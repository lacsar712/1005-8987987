import os
import re
import uuid
import threading
import tempfile
from datetime import datetime
from urllib.parse import urlparse, urljoin
from ..db import db, UrlImportTask, UrlImportItem, Photo, Album
from .phash_service import compute_phash, find_duplicate_in_album, PHASH_DISTANCE_THRESHOLD
from PIL import Image, ExifTags


ALLOWED_CONTENT_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'
}
MAX_FILE_SIZE = 20 * 1024 * 1024
HTTP_TIMEOUT = 30


def _get_http_client():
    try:
        import requests
        return requests
    except ImportError:
        return None


def _get_html_parser():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError:
        return None


def is_image_url(url):
    """判断 URL 是否指向图片（基于扩展名）"""
    ext_pattern = re.compile(r'\.(jpg|jpeg|png|gif|webp)(\?.*)?$', re.IGNORECASE)
    return bool(ext_pattern.search(url))


def extract_urls_from_text(text):
    """从多行文本中提取所有 http/https URL"""
    if not text:
        return []
    url_pattern = re.compile(r'https?://[^\s]+', re.IGNORECASE)
    urls = url_pattern.findall(text)
    cleaned = []
    for url in urls:
        url = url.strip().rstrip(').,;]')
        if url:
            cleaned.append(url)
    return list(dict.fromkeys(cleaned))


def extract_img_urls_from_page(page_url):
    """从网页 HTML 中提取所有 img 标签的 src URL"""
    requests_lib = _get_http_client()
    bs4 = _get_html_parser()
    if not requests_lib or not bs4:
        return [], '缺少依赖：requests 或 beautifulsoup4 未安装'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests_lib.get(page_url, headers=headers, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'application/xhtml' not in content_type:
            return [], '目标 URL 不是 HTML 页面'

        soup = bs4(resp.text, 'html.parser')
        base_url = page_url
        base_tag = soup.find('base')
        if base_tag and base_tag.get('href'):
            base_url = urljoin(page_url, base_tag['href'])

        img_urls = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not src:
                continue
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                src = urljoin(base_url, src)
            elif not src.startswith('http'):
                src = urljoin(base_url, src)
            if src.startswith('http'):
                img_urls.append(src)

        unique_urls = list(dict.fromkeys(img_urls))
        return unique_urls, None
    except Exception as e:
        return [], f'解析页面失败: {str(e)}'


def _download_to_temp(url):
    """下载 URL 内容到临时文件，返回 (temp_path, content_type, file_size, error)"""
    requests_lib = _get_http_client()
    if not requests_lib:
        return None, '', 0, '缺少依赖：requests 未安装'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests_lib.get(url, headers=headers, timeout=HTTP_TIMEOUT, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
        content_length = resp.headers.get('Content-Length')
        if content_length:
            try:
                size = int(content_length)
                if size > MAX_FILE_SIZE:
                    return None, content_type, size, f'文件过大（{size // 1024 // 1024}MB），超过限制 {MAX_FILE_SIZE // 1024 // 1024}MB'
            except (ValueError, TypeError):
                pass

        tmp_fd, tmp_path = tempfile.mkstemp(prefix='url_import_')
        os.close(tmp_fd)

        total_size = 0
        with open(tmp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    if total_size > MAX_FILE_SIZE:
                        os.unlink(tmp_path)
                        return None, content_type, total_size, f'文件过大，超过限制 {MAX_FILE_SIZE // 1024 // 1024}MB'

        return tmp_path, content_type, total_size, None
    except Exception as e:
        return None, '', 0, f'下载失败: {str(e)}'


def _validate_image_content(temp_path, content_type):
    """校验下载的内容是否为有效图片，返回 (is_valid, width, height, exif_info, error)"""
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return False, None, None, None, f'不支持的 Content-Type: {content_type}'

    try:
        with Image.open(temp_path) as img:
            img.verify()
        with Image.open(temp_path) as img:
            width, height = img.size
            exif_taken_at = None
            exif_camera_model = None
            try:
                exif_data = img._getexif()
                if exif_data:
                    exif_tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif_data.items()}
                    date_str = exif_tag_map.get('DateTimeOriginal') or exif_tag_map.get('DateTime')
                    if date_str:
                        try:
                            exif_taken_at = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                        except (ValueError, TypeError):
                            pass
                    make = exif_tag_map.get('Make', '') or ''
                    model = exif_tag_map.get('Model', '') or ''
                    camera_parts = [p.strip() for p in [make, model] if p and p.strip()]
                    if camera_parts:
                        exif_camera_model = ' '.join(camera_parts)[:100] or None
            except Exception:
                pass
            return True, width, height, (exif_taken_at, exif_camera_model), None
    except Exception as e:
        return False, None, None, None, f'图片内容校验失败: {str(e)}'


class UrlImportProcessor:
    """URL 导入后台任务处理器"""

    _current_tasks = {}
    _lock = threading.Lock()
    _threads = {}

    def __init__(self, uploads_folder):
        self.uploads_folder = uploads_folder

    def get_task(self, task_id):
        return UrlImportTask.query.get(task_id)

    def list_recent_tasks(self, limit=10):
        return UrlImportTask.query.order_by(UrlImportTask.created_at.desc()).limit(limit).all()

    def is_task_running(self, task_id):
        with self._lock:
            thread = self._threads.get(task_id)
            return thread is not None and thread.is_alive()

    def any_running(self):
        with self._lock:
            return any(t is not None and t.is_alive() for t in self._threads.values())

    def start_task(self, album_id, source_type, source_data):
        """
        创建并启动导入任务
        source_type: 'urls' 或 'page'
        source_data: 多行 URL 文本，或网页 URL
        """
        album = Album.query.get(album_id)
        if not album:
            return None, '相册不存在'

        urls = []
        if source_type == 'urls':
            urls = extract_urls_from_text(source_data)
            if not urls:
                return None, '未从输入中解析到有效的 URL'
        elif source_type == 'page':
            page_urls, err = extract_img_urls_from_page(source_data)
            if err:
                return None, err
            urls = page_urls
            if not urls:
                return None, '页面中未找到图片链接'

        task = UrlImportTask(
            album_id=album_id,
            status='pending',
            total=len(urls),
            processed=0,
            succeeded=0,
            failed=0,
            duplicates=0,
            pending_decisions=0,
            started_at=datetime.utcnow(),
        )
        db.session.add(task)
        db.session.flush()

        for url in urls:
            item = UrlImportItem(
                task_id=task.id,
                source_url=url[:1000],
                status='pending',
            )
            db.session.add(item)

        db.session.commit()

        with self._lock:
            if self.any_running():
                pass
            thread = threading.Thread(
                target=self._run_task,
                args=(task.id,),
                daemon=True
            )
            self._threads[task.id] = thread
            thread.start()

        return task, None

    def _run_task(self, task_id):
        from ..app import create_app
        app = create_app()
        with app.app_context():
            task = UrlImportTask.query.get(task_id)
            if not task:
                return

            task.status = 'running'
            db.session.commit()

            items = UrlImportItem.query.filter_by(task_id=task_id).order_by(UrlImportItem.id.asc()).all()

            for item in items:
                self._process_item(task, item)

            task = UrlImportTask.query.get(task_id)
            if task:
                if task.pending_decisions > 0:
                    task.status = 'awaiting_decision'
                elif task.failed > 0 and task.succeeded == 0:
                    task.status = 'failed'
                elif task.failed > 0:
                    task.status = 'completed_with_errors'
                else:
                    task.status = 'completed'
                task.completed_at = datetime.utcnow()
                db.session.commit()

            with self._lock:
                self._threads.pop(task_id, None)

    def _process_item(self, task, item):
        item.status = 'downloading'
        db.session.commit()

        temp_path, content_type, file_size, err = _download_to_temp(item.source_url)
        if err:
            item.status = 'failed'
            item.error_message = err
            item.content_type = content_type
            item.file_size = file_size
            task.processed += 1
            task.failed += 1
            db.session.commit()
            return

        item.content_type = content_type
        item.file_size = file_size

        is_valid, width, height, exif_info, err = _validate_image_content(temp_path, content_type)
        if not is_valid:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            item.status = 'failed'
            item.error_message = err
            task.processed += 1
            task.failed += 1
            db.session.commit()
            return

        item.width = width
        item.height = height

        try:
            with Image.open(temp_path) as img_obj:
                phash_val = compute_phash(image_obj=img_obj)
        except Exception:
            phash_val = None

        item.phash = phash_val or ''

        if phash_val:
            dup_photo, distance = find_duplicate_in_album(task.album_id, phash_val)
            if dup_photo:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                item.status = 'duplicate'
                item.duplicate_photo_id = dup_photo.id
                item.duplicate_distance = distance
                task.processed += 1
                task.duplicates += 1
                task.pending_decisions += 1
                db.session.commit()
                return

        parsed = urlparse(item.source_url)
        original_filename = os.path.basename(parsed.path) or 'image'
        if '.' not in original_filename:
            ext_map = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}
            original_filename += ext_map.get(content_type, '.jpg')
        item.original_filename = original_filename

        ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        unique_filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(self.uploads_folder, unique_filename)

        try:
            import shutil
            shutil.move(temp_path, save_path)
        except Exception as e:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            item.status = 'failed'
            item.error_message = f'保存文件失败: {str(e)}'
            task.processed += 1
            task.failed += 1
            db.session.commit()
            return

        item.saved_filename = unique_filename

        exif_taken_at, exif_camera_model = exif_info or (None, None)
        new_photo = Photo(
            filename=unique_filename,
            original_filename=original_filename,
            album_id=task.album_id,
            exif_taken_at=exif_taken_at,
            exif_camera_model=exif_camera_model,
            width=width,
            height=height,
            phash=phash_val or '',
        )
        db.session.add(new_photo)
        db.session.flush()

        item.photo_id = new_photo.id
        item.status = 'success'
        task.processed += 1
        task.succeeded += 1
        db.session.commit()

    def resolve_decision(self, item_id, decision, album_id=None):
        """
        处理疑似重复项的决策
        decision: 'import'（仍要导入）或 'skip'（跳过）
        """
        item = UrlImportItem.query.get(item_id)
        if not item:
            return False, '记录不存在'
        if item.status != 'duplicate':
            return False, '该条目无需决策'

        task = UrlImportTask.query.get(item.task_id)
        if not task:
            return False, '任务不存在'

        effective_album_id = album_id or task.album_id

        if decision == 'skip':
            item.status = 'skipped'
            item.decision = 'skip'
            task.pending_decisions -= 1
            if task.pending_decisions <= 0 and task.status == 'awaiting_decision':
                task.status = 'completed'
                task.completed_at = datetime.utcnow()
            db.session.commit()
            return True, None

        if decision == 'import':
            temp_path, content_type, file_size, err = _download_to_temp(item.source_url)
            if err:
                item.status = 'failed'
                item.error_message = err
                item.decision = 'import'
                task.pending_decisions -= 1
                task.failed += 1
                db.session.commit()
                return False, err

            is_valid, width, height, exif_info, err = _validate_image_content(temp_path, content_type)
            if not is_valid:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                item.status = 'failed'
                item.error_message = err
                item.decision = 'import'
                task.pending_decisions -= 1
                task.failed += 1
                db.session.commit()
                return False, err

            original_filename = item.original_filename or 'image'
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
            unique_filename = f"{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(self.uploads_folder, unique_filename)

            try:
                import shutil
                shutil.move(temp_path, save_path)
            except Exception as e:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                return False, f'保存文件失败: {str(e)}'

            exif_taken_at, exif_camera_model = exif_info or (None, None)
            new_photo = Photo(
                filename=unique_filename,
                original_filename=original_filename,
                album_id=effective_album_id,
                exif_taken_at=exif_taken_at,
                exif_camera_model=exif_camera_model,
                width=width,
                height=height,
                phash=item.phash or '',
            )
            db.session.add(new_photo)
            db.session.flush()

            item.photo_id = new_photo.id
            item.saved_filename = unique_filename
            item.status = 'success'
            item.decision = 'import'
            task.pending_decisions -= 1
            task.succeeded += 1
            if task.pending_decisions <= 0 and task.status == 'awaiting_decision':
                task.status = 'completed'
                task.completed_at = datetime.utcnow()
            db.session.commit()
            return True, None

        return False, '无效的决策选项'

    def get_task_items(self, task_id, status_filter=None):
        query = UrlImportItem.query.filter_by(task_id=task_id)
        if status_filter:
            query = query.filter_by(status=status_filter)
        return query.order_by(UrlImportItem.id.asc()).all()
