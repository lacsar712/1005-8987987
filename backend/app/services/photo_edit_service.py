import os
import json
import shutil
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
from ..db import db, Photo, PhotoEditVersion


class PhotoEditService:
    """照片编辑服务：非破坏性编辑、版本管理、合成应用"""

    @staticmethod
    def _get_upload_folder():
        from flask import current_app
        return current_app.config['UPLOAD_FOLDER']

    @staticmethod
    def _get_sidecar_path(filename):
        upload_folder = PhotoEditService._get_upload_folder()
        base, ext = os.path.splitext(filename)
        return os.path.join(upload_folder, f'{base}.edit.json')

    @staticmethod
    def _get_original_path(filename):
        upload_folder = PhotoEditService._get_upload_folder()
        base, ext = os.path.splitext(filename)
        return os.path.join(upload_folder, f'{base}_original{ext}')

    @staticmethod
    def ensure_original_backup(photo):
        """确保原图存在备份（{uuid}_original.ext），如不存在则从当前文件复制"""
        upload_folder = PhotoEditService._get_upload_folder()
        current_path = os.path.join(upload_folder, photo.filename)
        original_path = PhotoEditService._get_original_path(photo.filename)

        if not os.path.exists(original_path) and os.path.exists(current_path):
            shutil.copy2(current_path, original_path)
        return original_path

    @staticmethod
    def read_sidecar(filename):
        """读取 .edit.json sidecar 文件"""
        path = PhotoEditService._get_sidecar_path(filename)
        if not os.path.exists(path):
            return {'operations': [], 'history': []}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {'operations': [], 'history': []}

    @staticmethod
    def write_sidecar(filename, data):
        """写入 .edit.json sidecar 文件"""
        path = PhotoEditService._get_sidecar_path(filename)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    @staticmethod
    def list_versions(photo_id):
        """列出照片的所有编辑版本"""
        versions = PhotoEditVersion.query.filter_by(photo_id=photo_id)\
            .order_by(PhotoEditVersion.version_number.desc()).all()
        return versions

    @staticmethod
    def save_version(photo_id, operations, label='', thumbnail=''):
        """保存一个新的编辑版本（非破坏性保存操作序列）"""
        photo = Photo.query.get(photo_id)
        if not photo:
            return None, '照片不存在'

        PhotoEditService.ensure_original_backup(photo)

        max_version = db.session.query(
            db.func.max(PhotoEditVersion.version_number)
        ).filter_by(photo_id=photo_id).scalar() or 0

        version = PhotoEditVersion(
            photo_id=photo_id,
            version_number=max_version + 1,
            label=label or f'版本 {max_version + 1}',
            thumbnail_data=thumbnail,
            is_applied=False,
        )
        version.set_operations(operations)
        db.session.add(version)

        sidecar = PhotoEditService.read_sidecar(photo.filename)
        if 'history' not in sidecar:
            sidecar['history'] = []
        sidecar['history'].append({
            'version': version.version_number,
            'operations': operations,
            'label': version.label,
            'created_at': datetime.utcnow().isoformat(),
        })
        sidecar['operations'] = operations
        PhotoEditService.write_sidecar(photo.filename, sidecar)

        db.session.commit()
        return version, None

    @staticmethod
    def get_version(version_id):
        return PhotoEditVersion.query.get(version_id)

    @staticmethod
    def rollback_to_version(photo_id, version_id):
        """回滚到指定版本（将该版本标记为已应用，操作序列同步到 sidecar）"""
        photo = Photo.query.get(photo_id)
        if not photo:
            return False, '照片不存在'

        version = PhotoEditVersion.query.filter_by(id=version_id, photo_id=photo_id).first()
        if not version:
            return False, '版本不存在'

        PhotoEditVersion.query.filter_by(photo_id=photo_id).update({'is_applied': False})
        version.is_applied = True

        sidecar = PhotoEditService.read_sidecar(photo.filename)
        sidecar['operations'] = version.get_operations()
        sidecar['current_version'] = version.version_number
        PhotoEditService.write_sidecar(photo.filename, sidecar)

        db.session.commit()
        return True, None

    @staticmethod
    def apply_operations_to_image(img, operations):
        """将编辑操作序列应用到 PIL Image 对象"""
        result = img.copy()
        width, height = result.size

        for op in operations:
            op_type = op.get('type')
            params = op.get('params', {})

            if op_type == 'rotate':
                angle = float(params.get('angle', 0))
                result = result.rotate(-angle, expand=True, resample=Image.BICUBIC)

            elif op_type == 'crop':
                x = int(params.get('x', 0))
                y = int(params.get('y', 0))
                w = int(params.get('width', result.width))
                h = int(params.get('height', result.height))
                x = max(0, min(x, result.width))
                y = max(0, min(y, result.height))
                w = max(1, min(w, result.width - x))
                h = max(1, min(h, result.height - y))
                result = result.crop((x, y, x + w, y + h))

            elif op_type == 'brightness':
                factor = float(params.get('value', 1.0))
                enhancer = ImageEnhance.Brightness(result)
                result = enhancer.enhance(factor)

            elif op_type == 'contrast':
                factor = float(params.get('value', 1.0))
                enhancer = ImageEnhance.Contrast(result)
                result = enhancer.enhance(factor)

            elif op_type == 'mosaic':
                shape = params.get('shape', 'rect')
                cell_size = int(params.get('cell_size', 10))
                x = int(params.get('x', 0))
                y = int(params.get('y', 0))
                w = int(params.get('width', 0))
                h = int(params.get('height', 0))

                if shape == 'circle':
                    cx = x + w // 2
                    cy = y + h // 2
                    radius = min(w, h) // 2
                    mask = Image.new('L', result.size, 0)
                    draw = ImageDraw.Draw(mask)
                    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=255)
                else:
                    mask = Image.new('L', result.size, 0)
                    draw = ImageDraw.Draw(mask)
                    draw.rectangle([x, y, x + w, y + h], fill=255)

                region = result.crop((x, y, x + w, y + h))
                region_small = region.resize(
                    (max(1, w // cell_size), max(1, h // cell_size)),
                    Image.NEAREST
                )
                mosaic_region = region_small.resize(region.size, Image.NEAREST)
                result.paste(mosaic_region, (x, y), mask.crop((x, y, x + w, y + h)))

        return result

    @staticmethod
    def commit_edit(photo_id, operations):
        """将编辑结果合成并覆盖 uploads 中的主文件，刷新 uploaded_at"""
        photo = Photo.query.get(photo_id)
        if not photo:
            return False, '照片不存在'

        upload_folder = PhotoEditService._get_upload_folder()
        current_path = os.path.join(upload_folder, photo.filename)

        PhotoEditService.ensure_original_backup(photo)
        original_path = PhotoEditService._get_original_path(photo.filename)

        try:
            with Image.open(original_path) as img:
                img = img.convert('RGB') if img.mode not in ('RGB', 'RGBA') else img
                result = PhotoEditService.apply_operations_to_image(img, operations)

                ext = os.path.splitext(photo.filename)[1].lower()
                save_format = 'JPEG' if ext in ('.jpg', '.jpeg') else (
                    'PNG' if ext == '.png' else ('WEBP' if ext == '.webp' else 'PNG')
                )

                if save_format == 'JPEG' and result.mode == 'RGBA':
                    background = Image.new('RGB', result.size, (255, 255, 255))
                    background.paste(result, mask=result.split()[3])
                    result = background

                result.save(current_path, format=save_format, quality=95)

            try:
                with Image.open(current_path) as updated_img:
                    photo.width, photo.height = updated_img.size
            except Exception:
                pass

            photo.uploaded_at = datetime.utcnow()
            db.session.commit()

            return True, None
        except Exception as e:
            return False, f'合成图片失败: {str(e)}'

    @staticmethod
    def get_photo_edit_info(photo):
        """获取照片的完整编辑信息（供前端使用）"""
        upload_folder = PhotoEditService._get_upload_folder()
        sidecar = PhotoEditService.read_sidecar(photo.filename)
        versions = PhotoEditService.list_versions(photo.id)

        original_path = PhotoEditService._get_original_path(photo.filename)
        has_original = os.path.exists(original_path)

        return {
            'photo': {
                'id': photo.id,
                'filename': photo.filename,
                'original_filename': photo.original_filename,
                'width': photo.width,
                'height': photo.height,
                'album_id': photo.album_id,
            },
            'current_operations': sidecar.get('operations', []),
            'has_original_backup': has_original,
            'versions': [v.to_dict() for v in versions],
        }
