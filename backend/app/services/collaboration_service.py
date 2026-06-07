import os
import uuid
import secrets
from datetime import datetime, timedelta
from flask import url_for, current_app
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
from ..db import db, Album, Photo, PhotoPlaceholder, CollaborationLink, CollaborationPhoto
from . import compute_phash, AlbumWatermarkService, WatermarkProcessor, PlaceholderService


def _generate_token():
    return secrets.token_urlsafe(32)


class CollaborationLinkService:
    @staticmethod
    def create_link(album_id, name='', expires_hours=None, max_uploads=0, created_by='admin'):
        album = Album.query.get(album_id)
        if not album:
            return None, '相册不存在'

        token = _generate_token()
        link = CollaborationLink(
            token=token,
            album_id=album_id,
            name=name or f'{album.title} - 协作链接',
            max_uploads=max_uploads or 0,
            is_active=True,
            created_by=created_by,
        )
        if expires_hours and expires_hours > 0:
            link.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        db.session.add(link)
        db.session.commit()
        return link, None

    @staticmethod
    def get_by_token(token):
        return CollaborationLink.query.filter_by(token=token).first()

    @staticmethod
    def get_by_id(link_id):
        return CollaborationLink.query.get(link_id)

    @staticmethod
    def list_by_album(album_id):
        return CollaborationLink.query.filter_by(album_id=album_id).order_by(CollaborationLink.created_at.desc()).all()

    @staticmethod
    def list_all():
        return CollaborationLink.query.order_by(CollaborationLink.created_at.desc()).all()

    @staticmethod
    def revoke(link_id):
        link = CollaborationLink.query.get(link_id)
        if not link:
            return None
        link.is_active = False
        db.session.commit()
        return link

    @staticmethod
    def reactivate(link_id):
        link = CollaborationLink.query.get(link_id)
        if not link:
            return None
        link.is_active = True
        db.session.commit()
        return link

    @staticmethod
    def delete(link_id):
        link = CollaborationLink.query.get(link_id)
        if not link:
            return False
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        for photo in link.photos:
            if photo.status != 'approved' and photo.filename:
                try:
                    fp = os.path.join(upload_folder, photo.filename)
                    if os.path.exists(fp):
                        os.remove(fp)
                except OSError:
                    pass
        db.session.delete(link)
        db.session.commit()
        return True

    @staticmethod
    def update(link_id, name=None, expires_hours=None, max_uploads=None):
        link = CollaborationLink.query.get(link_id)
        if not link:
            return None
        if name is not None:
            link.name = name
        if max_uploads is not None:
            link.max_uploads = max_uploads or 0
        if expires_hours is not None:
            if expires_hours > 0:
                link.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
            else:
                link.expires_at = None
        db.session.commit()
        return link


class CollaborationPhotoService:
    @staticmethod
    def _allowed_file(filename):
        allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

    @staticmethod
    def upload_photo(link, file, contributor_name='', message=''):
        if not link or not link.is_valid():
            return None, '协作链接无效或已过期'

        if not file or not file.filename:
            return None, '没有文件被上传'

        if not CollaborationPhotoService._allowed_file(file.filename):
            return None, '不支持的文件格式'

        original_filename = secure_filename(file.filename) or '未命名图片'
        try:
            extension = file.filename.rsplit('.', 1)[1].lower()
        except IndexError:
            return None, '无效的文件名'

        upload_folder = current_app.config['UPLOAD_FOLDER']
        unique_filename = f"{uuid.uuid4().hex}.{extension}"
        save_path = os.path.join(upload_folder, unique_filename)
        file.save(save_path)

        width, height = None, None
        exif_taken_at = None
        exif_camera_model = None
        try:
            with Image.open(save_path) as img:
                width, height = img.size
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
        except Exception:
            pass

        try:
            resolved = AlbumWatermarkService.resolve_effective_config(link.album_id)
            if resolved and resolved['enabled']:
                try:
                    wm_processor = WatermarkProcessor(upload_folder)
                    wm_processor.process_image(
                        save_path,
                        resolved['config'],
                        effective_text=resolved['effective_text'],
                        effective_position=resolved['effective_position'],
                    )
                except Exception:
                    pass
        except Exception:
            pass

        collab_photo = CollaborationPhoto(
            link_id=link.id,
            album_id=link.album_id,
            filename=unique_filename,
            original_filename=original_filename,
            contributor_name=contributor_name or '',
            message=message or '',
            status='pending',
            width=width,
            height=height,
            exif_taken_at=exif_taken_at,
            exif_camera_model=exif_camera_model,
        )
        db.session.add(collab_photo)
        db.session.commit()
        return collab_photo, None

    @staticmethod
    def list_pending(album_id=None, link_id=None):
        query = CollaborationPhoto.query.filter_by(status='pending')
        if album_id:
            query = query.filter_by(album_id=album_id)
        if link_id:
            query = query.filter_by(link_id=link_id)
        return query.order_by(CollaborationPhoto.uploaded_at.asc()).all()

    @staticmethod
    def list_by_album(album_id, status=None):
        query = CollaborationPhoto.query.filter_by(album_id=album_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(CollaborationPhoto.uploaded_at.desc()).all()

    @staticmethod
    def get_by_id(photo_id):
        return CollaborationPhoto.query.get(photo_id)

    @staticmethod
    def approve(collab_photo_id, reviewed_by='admin'):
        collab_photo = CollaborationPhoto.query.get(collab_photo_id)
        if not collab_photo or collab_photo.status != 'pending':
            return None, '照片不存在或已处理'

        photo_phash = ''
        try:
            upload_folder = current_app.config['UPLOAD_FOLDER']
            fp = os.path.join(upload_folder, collab_photo.filename)
            photo_phash = compute_phash(image_path=fp) or ''
        except Exception:
            pass

        photo_aspect_ratio = None
        if collab_photo.width and collab_photo.height and collab_photo.height > 0:
            photo_aspect_ratio = round(collab_photo.width / collab_photo.height, 2)

        new_photo = Photo(
            filename=collab_photo.filename,
            original_filename=collab_photo.original_filename,
            album_id=collab_photo.album_id,
            exif_taken_at=collab_photo.exif_taken_at,
            exif_camera_model=collab_photo.exif_camera_model,
            width=collab_photo.width,
            height=collab_photo.height,
            phash=photo_phash,
        )

        try:
            placeholders = PhotoPlaceholder.query.filter_by(album_id=collab_photo.album_id).all()
            matched = PlaceholderService.find_best_matching_placeholder(placeholders, photo_aspect_ratio)
            if matched:
                new_photo.replaced_placeholder_id = matched.id
                matched.is_replaced = True
        except Exception:
            pass

        db.session.add(new_photo)
        db.session.flush()

        collab_photo.status = 'approved'
        collab_photo.photo_id = new_photo.id
        collab_photo.reviewed_at = datetime.utcnow()
        collab_photo.reviewed_by = reviewed_by
        db.session.commit()

        return collab_photo, None

    @staticmethod
    def reject(collab_photo_id, reviewed_by='admin'):
        collab_photo = CollaborationPhoto.query.get(collab_photo_id)
        if not collab_photo or collab_photo.status != 'pending':
            return None, '照片不存在或已处理'

        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if collab_photo.filename:
            try:
                fp = os.path.join(upload_folder, collab_photo.filename)
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass

        collab_photo.status = 'rejected'
        collab_photo.reviewed_at = datetime.utcnow()
        collab_photo.reviewed_by = reviewed_by
        db.session.commit()
        return collab_photo, None

    @staticmethod
    def batch_approve(photo_ids, reviewed_by='admin'):
        results = []
        errors = []
        for pid in photo_ids:
            try:
                photo, err = CollaborationPhotoService.approve(pid, reviewed_by)
                if photo:
                    results.append(photo)
                else:
                    errors.append(f'ID {pid}: {err}')
            except Exception as e:
                errors.append(f'ID {pid}: {str(e)}')
        return results, errors

    @staticmethod
    def batch_reject(photo_ids, reviewed_by='admin'):
        results = []
        errors = []
        for pid in photo_ids:
            try:
                photo, err = CollaborationPhotoService.reject(pid, reviewed_by)
                if photo:
                    results.append(photo)
                else:
                    errors.append(f'ID {pid}: {err}')
            except Exception as e:
                errors.append(f'ID {pid}: {str(e)}')
        return results, errors

    @staticmethod
    def get_pending_stats():
        pending_count = CollaborationPhoto.query.filter_by(status='pending').count()
        by_album = {}
        for cp in CollaborationPhoto.query.filter_by(status='pending').all():
            by_album.setdefault(cp.album_id, 0)
            by_album[cp.album_id] += 1
        return {
            'total_pending': pending_count,
            'by_album': by_album,
        }
