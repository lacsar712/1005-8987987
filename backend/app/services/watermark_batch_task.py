import os
import threading
from datetime import datetime
from ..db import db, WatermarkBatchTask, Photo, Album
from .watermark_service import AlbumWatermarkService, WatermarkConfigService
from .watermark_processor import WatermarkProcessor


class WatermarkBatchProcessor:
    """批量补打水印后台任务：使用线程逐张处理历史照片"""

    _current_task = None
    _lock = threading.Lock()
    _thread = None

    def __init__(self, uploads_folder, watermark_images_folder=None):
        self.uploads_folder = uploads_folder
        self.processor = WatermarkProcessor(uploads_folder, watermark_images_folder)

    def get_latest_task(self):
        """获取最近一次批量任务"""
        return WatermarkBatchTask.query.order_by(WatermarkBatchTask.created_at.desc()).first()

    def get_task(self, task_id):
        """按 ID 获取任务"""
        return WatermarkBatchTask.query.get(task_id)

    def is_running(self):
        """检查是否有任务正在运行"""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start_task(self, album_id=None):
        """
        启动批量补打任务
        :param album_id: 可选，只处理指定相册
        :return: WatermarkBatchTask 或 None（如果已有任务运行中）
        """
        with self._lock:
            if self.is_running():
                return None

        query = Photo.query
        if album_id:
            query = query.filter_by(album_id=album_id)
        photos = query.all()

        if not photos:
            return None

        task = WatermarkBatchTask(
            status='pending',
            total=len(photos),
            processed=0,
            failed_count=0,
            album_id=album_id,
            started_at=datetime.utcnow(),
        )
        db.session.add(task)
        db.session.commit()

        self._current_task = task
        self._thread = threading.Thread(
            target=self._run_task,
            args=(task.id, album_id),
            daemon=True
        )
        self._thread.start()
        return task

    def _run_task(self, task_id, album_id):
        """后台线程执行批量处理"""
        from ..app import create_app

        app = create_app()
        with app.app_context():
            task = WatermarkBatchTask.query.get(task_id)
            if not task:
                return

            task.status = 'running'
            db.session.commit()

            query = Photo.query
            if album_id:
                query = query.filter_by(album_id=album_id)
            photos = query.all()

            global_config = WatermarkConfigService.get_config()

            processed = 0
            failed = 0
            errors = []

            for photo in photos:
                try:
                    resolved = AlbumWatermarkService.resolve_effective_config(photo.album_id)
                    if resolved and resolved['enabled']:
                        image_path = os.path.join(self.uploads_folder, photo.filename)
                        if os.path.exists(image_path):
                            self.processor.process_image(
                                image_path,
                                resolved['config'],
                                effective_text=resolved['effective_text'],
                                effective_position=resolved['effective_position'],
                            )
                    processed += 1
                except Exception as e:
                    failed += 1
                    errors.append(f'Photo {photo.id}: {str(e)}')

                task = WatermarkBatchTask.query.get(task_id)
                if task:
                    task.processed = processed
                    task.failed_count = failed
                    db.session.commit()

            task = WatermarkBatchTask.query.get(task_id)
            if task:
                task.status = 'completed' if failed == 0 else 'completed_with_errors'
                task.completed_at = datetime.utcnow()
                if errors:
                    task.error_message = '\n'.join(errors[:50])
                db.session.commit()

            with self._lock:
                self._thread = None
                self._current_task = None
