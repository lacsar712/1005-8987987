import os
import threading
from datetime import datetime
from ..db import db, WatermarkBatchTask, Photo
from .watermark_service import AlbumWatermarkService, WatermarkConfigService
from .watermark_processor import WatermarkProcessor


class WatermarkBatchProcessor:
    """批量补打水印后台任务：使用线程逐张处理历史照片"""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, uploads_folder, flask_app, watermark_images_folder=None):
        self.uploads_folder = uploads_folder
        self.flask_app = flask_app
        self.processor = WatermarkProcessor(uploads_folder, watermark_images_folder)
        self._thread = None
        self._thread_lock = threading.Lock()

    @classmethod
    def get_instance(cls, uploads_folder=None, flask_app=None, watermark_images_folder=None):
        with cls._instance_lock:
            if cls._instance is None:
                if uploads_folder is None or flask_app is None:
                    return None
                cls._instance = cls(uploads_folder, flask_app, watermark_images_folder)
            return cls._instance

    def get_latest_task(self):
        with self.flask_app.app_context():
            return WatermarkBatchTask.query.order_by(WatermarkBatchTask.created_at.desc()).first()

    def get_task(self, task_id):
        with self.flask_app.app_context():
            return WatermarkBatchTask.query.get(task_id)

    def is_running(self):
        with self._thread_lock:
            return self._thread is not None and self._thread.is_alive()

    def start_task(self, album_id=None):
        with self._thread_lock:
            if self.is_running():
                return None

        with self.flask_app.app_context():
            query = Photo.query
            if album_id:
                query = query.filter_by(album_id=album_id)
            photos = query.all()

            if not photos:
                return None

            global_config = WatermarkConfigService.get_config()
            if not global_config.enabled:
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
            task_id = task.id

        self._thread = threading.Thread(
            target=self._run_task,
            args=(task_id, album_id),
            daemon=True
        )
        self._thread.start()

        with self.flask_app.app_context():
            return WatermarkBatchTask.query.get(task_id)

    def _run_task(self, task_id, album_id):
        with self.flask_app.app_context():
            task = WatermarkBatchTask.query.get(task_id)
            if not task:
                with self._thread_lock:
                    self._thread = None
                return

            task.status = 'running'
            db.session.commit()

            query = Photo.query
            if album_id:
                query = query.filter_by(album_id=album_id)
            photos = query.all()

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

                try:
                    task = WatermarkBatchTask.query.get(task_id)
                    if task:
                        task.processed = processed
                        task.failed_count = failed
                        db.session.commit()
                except Exception:
                    pass

            try:
                task = WatermarkBatchTask.query.get(task_id)
                if task:
                    task.status = 'completed' if failed == 0 else 'completed_with_errors'
                    task.completed_at = datetime.utcnow()
                    if errors:
                        task.error_message = '\n'.join(errors[:50])
                    db.session.commit()
            except Exception:
                pass

        with self._thread_lock:
            self._thread = None
