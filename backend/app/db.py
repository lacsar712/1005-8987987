import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

# 对已有 SQLite 表增量补列（create_all 不会 alter 旧表）
_SCHEMA_MIGRATIONS = {
    'album': [
        ('is_admin_only', 'BOOLEAN DEFAULT 0'),
        ('template_id', 'INTEGER'),
        ('layout_config', "TEXT DEFAULT '{}'"),
        ('tags', "TEXT DEFAULT '[]'"),
    ],
    'photo': [
        ('exif_taken_at', 'DATETIME'),
        ('exif_camera_model', 'VARCHAR(100)'),
        ('width', 'INTEGER'),
        ('height', 'INTEGER'),
        ('phash', "VARCHAR(64) DEFAULT ''"),
        ('replaced_placeholder_id', 'INTEGER'),
    ],
}


def migrate_schema():
    """为旧版数据库补齐模型新增列，避免启动时查询失败。"""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    for table_name, columns in _SCHEMA_MIGRATIONS.items():
        if table_name not in existing_tables:
            continue
        existing_cols = {col['name'] for col in inspector.get_columns(table_name)}
        for col_name, col_def in columns:
            if col_name not in existing_cols:
                db.session.execute(
                    text(f'ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}')
                )
    db.session.commit()


class Album(db.Model):
    """相册模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_admin_only = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    template_id = db.Column(db.Integer, db.ForeignKey('template.id'), nullable=True)
    layout_config = db.Column(db.Text, default='{}')
    tags = db.Column(db.Text, default='[]')
    photos = db.relationship('Photo', backref='album', lazy=True, cascade="all, delete-orphan")
    placeholders = db.relationship('PhotoPlaceholder', backref='album', lazy=True, cascade="all, delete-orphan")

    def get_layout_config(self):
        try:
            return json.loads(self.layout_config or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_layout_config(self, config):
        self.layout_config = json.dumps(config, ensure_ascii=False)

    def get_tags_list(self):
        try:
            return json.loads(self.tags or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_tags_list(self, tags):
        self.tags = json.dumps(tags, ensure_ascii=False)


class Photo(db.Model):
    """照片模型"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    exif_taken_at = db.Column(db.DateTime, nullable=True)
    exif_camera_model = db.Column(db.String(100), nullable=True)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    phash = db.Column(db.String(64), default='')
    replaced_placeholder_id = db.Column(db.Integer, db.ForeignKey('photo_placeholder.id'), nullable=True)
    highlights = db.relationship('Highlight', backref='photo', lazy=True, cascade="all, delete-orphan")

    @property
    def aspect_ratio(self):
        if self.width and self.height and self.height > 0:
            return round(self.width / self.height, 2)
        return None


class Highlight(db.Model):
    """精选照片关联表"""
    id = db.Column(db.Integer, primary_key=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CurationConfig(db.Model):
    """策展配置（策展语、幻灯片间隔等）"""
    id = db.Column(db.Integer, primary_key=True)
    curation_text = db.Column(db.Text, default='')
    slideshow_interval = db.Column(db.Integer, default=3)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Template(db.Model):
    """相册模板模型"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, default='')
    scene_description = db.Column(db.Text, default='')
    cover_placeholder = db.Column(db.Text, default='')
    prefill_description = db.Column(db.Text, default='')
    suggested_tags = db.Column(db.Text, default='[]')
    layout_params = db.Column(db.Text, default='{}')
    placeholder_svg_data = db.Column(db.Text, default='[]')
    is_builtin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    albums = db.relationship('Album', backref='template', lazy=True)

    def get_suggested_tags(self):
        try:
            return json.loads(self.suggested_tags or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_suggested_tags(self, tags):
        self.suggested_tags = json.dumps(tags, ensure_ascii=False)

    def get_layout_params(self):
        try:
            return json.loads(self.layout_params or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_layout_params(self, params):
        self.layout_params = json.dumps(params, ensure_ascii=False)

    def get_placeholder_svgs(self):
        try:
            return json.loads(self.placeholder_svg_data or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_placeholder_svgs(self, svgs):
        self.placeholder_svg_data = json.dumps(svgs, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'scene_description': self.scene_description,
            'cover_placeholder': self.cover_placeholder,
            'prefill_description': self.prefill_description,
            'suggested_tags': self.get_suggested_tags(),
            'layout_params': self.get_layout_params(),
            'placeholder_count': len(self.get_placeholder_svgs()),
            'is_builtin': self.is_builtin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PhotoPlaceholder(db.Model):
    """照片占位图模型"""
    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    svg_content = db.Column(db.Text, nullable=False)
    aspect_ratio = db.Column(db.Float, nullable=False)
    slot_index = db.Column(db.Integer, default=0)
    is_replaced = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    replaced_photo = db.relationship('Photo', backref='replaced_placeholder', lazy=True, uselist=False,
                                     foreign_keys='Photo.replaced_placeholder_id')


class WatermarkConfig(db.Model):
    """全局水印配置"""
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    watermark_type = db.Column(db.String(10), default='text')

    text_content = db.Column(db.String(200), default='© 在线相册')
    text_font_size = db.Column(db.Integer, default=32)
    text_opacity = db.Column(db.Float, default=0.6)
    text_color = db.Column(db.String(20), default='#ffffff')
    text_position = db.Column(db.String(20), default='bottom-right')
    text_tiling = db.Column(db.Boolean, default=False)
    text_tiling_spacing = db.Column(db.Integer, default=150)
    text_tiling_angle = db.Column(db.Integer, default=-30)
    text_stroke = db.Column(db.Boolean, default=True)
    text_stroke_color = db.Column(db.String(20), default='#000000')
    text_stroke_width = db.Column(db.Integer, default=2)

    image_filename = db.Column(db.String(200), default='')
    image_scale = db.Column(db.Float, default=0.15)
    image_opacity = db.Column(db.Float, default=0.7)
    image_position = db.Column(db.String(20), default='bottom-right')
    image_tiling = db.Column(db.Boolean, default=False)
    image_tiling_spacing = db.Column(db.Integer, default=200)
    image_tiling_angle = db.Column(db.Integer, default=0)

    adaptive_contrast = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'enabled': self.enabled,
            'watermark_type': self.watermark_type,
            'text_content': self.text_content,
            'text_font_size': self.text_font_size,
            'text_opacity': self.text_opacity,
            'text_color': self.text_color,
            'text_position': self.text_position,
            'text_tiling': self.text_tiling,
            'text_tiling_spacing': self.text_tiling_spacing,
            'text_tiling_angle': self.text_tiling_angle,
            'text_stroke': self.text_stroke,
            'text_stroke_color': self.text_stroke_color,
            'text_stroke_width': self.text_stroke_width,
            'image_filename': self.image_filename,
            'image_scale': self.image_scale,
            'image_opacity': self.image_opacity,
            'image_position': self.image_position,
            'image_tiling': self.image_tiling,
            'image_tiling_spacing': self.image_tiling_spacing,
            'image_tiling_angle': self.image_tiling_angle,
            'adaptive_contrast': self.adaptive_contrast,
        }


class AlbumWatermarkOverride(db.Model):
    """相册级水印覆盖配置"""
    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, default=True)
    override_text = db.Column(db.Boolean, default=False)
    override_position = db.Column(db.Boolean, default=False)
    text_content = db.Column(db.String(200), default='')
    text_position = db.Column(db.String(20), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    album = db.relationship('Album', backref=db.backref('watermark_override', uselist=False, lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'album_id': self.album_id,
            'enabled': self.enabled,
            'override_text': self.override_text,
            'override_position': self.override_position,
            'text_content': self.text_content,
            'text_position': self.text_position,
        }


class WatermarkBatchTask(db.Model):
    """批量补打水印任务"""
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='pending')
    total = db.Column(db.Integer, default=0)
    processed = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'total': self.total,
            'processed': self.processed,
            'failed_count': self.failed_count,
            'album_id': self.album_id,
            'progress': round(self.processed / self.total * 100, 1) if self.total > 0 else 0,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
        }


class RenameHistory(db.Model):
    """批量重命名历史记录（用于 undo 回滚）"""
    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=True)
    rule_description = db.Column(db.String(500), default='')
    snapshot = db.Column(db.Text, nullable=False)
    photo_count = db.Column(db.Integer, default=0)
    is_applied = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rolled_back_at = db.Column(db.DateTime, nullable=True)
    album = db.relationship('Album', backref=db.backref('rename_histories', lazy=True))

    def get_snapshot_data(self):
        try:
            return json.loads(self.snapshot or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_snapshot_data(self, data):
        self.snapshot = json.dumps(data, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'album_id': self.album_id,
            'album_title': self.album.title if self.album else None,
            'rule_description': self.rule_description,
            'photo_count': self.photo_count,
            'is_applied': self.is_applied,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'rolled_back_at': self.rolled_back_at.isoformat() if self.rolled_back_at else None,
        }


class PhotoEditVersion(db.Model):
    """照片编辑版本记录（用于非破坏性编辑历史）"""
    id = db.Column(db.Integer, primary_key=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=False)
    version_number = db.Column(db.Integer, default=1)
    label = db.Column(db.String(200), default='')
    operations_json = db.Column(db.Text, nullable=False)
    thumbnail_data = db.Column(db.Text, default='')
    is_applied = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photo = db.relationship('Photo', backref=db.backref('edit_versions', lazy=True, cascade="all, delete-orphan"))

    def get_operations(self):
        try:
            return json.loads(self.operations_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_operations(self, ops):
        self.operations_json = json.dumps(ops, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'photo_id': self.photo_id,
            'version_number': self.version_number,
            'label': self.label,
            'operations': self.get_operations(),
            'thumbnail': self.thumbnail_data or None,
            'is_applied': self.is_applied,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class GuestAccessConfig(db.Model):
    """访客访问控制配置"""
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    password = db.Column(db.String(20), default='')
    welcome_text = db.Column(db.String(500), default='欢迎访问，请输入访客口令')
    config_version = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'enabled': self.enabled,
            'password': self.password,
            'welcome_text': self.welcome_text,
            'config_version': self.config_version,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class GuestInviteCode(db.Model):
    """访客邀请码（QR码用）"""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_count = db.Column(db.Integer, default=0)
    max_uses = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    album_scope = db.Column(db.Text, default='')

    def get_album_scope_ids(self):
        try:
            return json.loads(self.album_scope or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_album_scope_ids(self, ids):
        self.album_scope = json.dumps(ids or [], ensure_ascii=False)

    def is_valid(self):
        if not self.is_active:
            return False
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            return False
        return datetime.utcnow() < self.expires_at

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'used_count': self.used_count,
            'max_uses': self.max_uses,
            'is_active': self.is_active,
            'is_valid': self.is_valid(),
            'album_scope_ids': self.get_album_scope_ids(),
        }


class AlbumAccessToken(db.Model):
    """相册组访问令牌（分域访问）"""
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(100), default='')
    album_ids_json = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(50), default='admin')

    def get_album_ids(self):
        try:
            return json.loads(self.album_ids_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    def set_album_ids(self, ids):
        self.album_ids_json = json.dumps(ids or [], ensure_ascii=False)

    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_at and datetime.utcnow() >= self.expires_at:
            return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'name': self.name,
            'album_ids': self.get_album_ids(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_active': self.is_active,
            'is_valid': self.is_valid(),
        }


class UrlImportTask(db.Model):
    """URL 导入任务"""
    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    total = db.Column(db.Integer, default=0)
    processed = db.Column(db.Integer, default=0)
    succeeded = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    duplicates = db.Column(db.Integer, default=0)
    pending_decisions = db.Column(db.Integer, default=0)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('UrlImportItem', backref='task', lazy=True, cascade="all, delete-orphan")
    album = db.relationship('Album', backref=db.backref('import_tasks', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'album_id': self.album_id,
            'album_title': self.album.title if self.album else None,
            'status': self.status,
            'total': self.total,
            'processed': self.processed,
            'succeeded': self.succeeded,
            'failed': self.failed,
            'duplicates': self.duplicates,
            'pending_decisions': self.pending_decisions,
            'progress': round(self.processed / self.total * 100, 1) if self.total > 0 else 0,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class UrlImportItem(db.Model):
    """URL 导入任务中的单条记录"""
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('url_import_task.id'), nullable=False)
    source_url = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), default='pending')
    error_message = db.Column(db.Text, default='')
    phash = db.Column(db.String(64), default='')
    duplicate_photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=True)
    duplicate_distance = db.Column(db.Integer, nullable=True)
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=True)
    saved_filename = db.Column(db.String(200), default='')
    original_filename = db.Column(db.String(200), default='')
    content_type = db.Column(db.String(100), default='')
    file_size = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    decision = db.Column(db.String(20), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    photo = db.relationship('Photo', foreign_keys=[photo_id], backref=db.backref('import_items', lazy=True))
    duplicate_photo = db.relationship('Photo', foreign_keys=[duplicate_photo_id])

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'source_url': self.source_url,
            'status': self.status,
            'error_message': self.error_message,
            'phash': self.phash or None,
            'duplicate_photo_id': self.duplicate_photo_id,
            'duplicate_distance': self.duplicate_distance,
            'photo_id': self.photo_id,
            'saved_filename': self.saved_filename or None,
            'original_filename': self.original_filename or None,
            'content_type': self.content_type or None,
            'file_size': self.file_size,
            'width': self.width,
            'height': self.height,
            'decision': self.decision or None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class CollaborationLink(db.Model):
    """协作上传链接"""
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    name = db.Column(db.String(100), default='')
    max_uploads = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(50), default='admin')
    album = db.relationship('Album', backref=db.backref('collaboration_links', lazy=True, cascade='all, delete-orphan'))
    photos = db.relationship('CollaborationPhoto', backref='link', lazy=True, cascade='all, delete-orphan')

    def is_valid(self):
        if not self.is_active:
            return False
        if self.expires_at and datetime.utcnow() >= self.expires_at:
            return False
        if self.max_uploads > 0:
            uploaded_count = CollaborationPhoto.query.filter_by(
                link_id=self.id
            ).filter(CollaborationPhoto.status != 'rejected').count()
            if uploaded_count >= self.max_uploads:
                return False
        return True

    def get_stats(self):
        photos = CollaborationPhoto.query.filter_by(link_id=self.id).all()
        total = len(photos)
        pending = sum(1 for p in photos if p.status == 'pending')
        approved = sum(1 for p in photos if p.status == 'approved')
        rejected = sum(1 for p in photos if p.status == 'rejected')
        return {
            'total': total,
            'pending': pending,
            'approved': approved,
            'rejected': rejected,
        }

    def to_dict(self, include_stats=True):
        data = {
            'id': self.id,
            'token': self.token,
            'album_id': self.album_id,
            'album_title': self.album.title if self.album else None,
            'name': self.name,
            'max_uploads': self.max_uploads,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_active': self.is_active,
            'is_valid': self.is_valid(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
        }
        if include_stats:
            data['stats'] = self.get_stats()
        return data


class CollaborationPhoto(db.Model):
    """协作上传的照片（待审核/已通过/已拒绝）"""
    id = db.Column(db.Integer, primary_key=True)
    link_id = db.Column(db.Integer, db.ForeignKey('collaboration_link.id'), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    filename = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    contributor_name = db.Column(db.String(100), default='')
    message = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='pending')
    photo_id = db.Column(db.Integer, db.ForeignKey('photo.id'), nullable=True)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    exif_taken_at = db.Column(db.DateTime, nullable=True)
    exif_camera_model = db.Column(db.String(100), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(50), default='')
    photo = db.relationship('Photo', foreign_keys=[photo_id], backref=db.backref('collaboration_photo', uselist=False, lazy=True))
    album = db.relationship('Album', backref=db.backref('collaboration_photos', lazy=True))

    def to_dict(self):
        from flask import url_for
        return {
            'id': self.id,
            'link_id': self.link_id,
            'album_id': self.album_id,
            'album_title': self.album.title if self.album else None,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'contributor_name': self.contributor_name,
            'message': self.message,
            'status': self.status,
            'photo_id': self.photo_id,
            'width': self.width,
            'height': self.height,
            'exif_taken_at': self.exif_taken_at.isoformat() if self.exif_taken_at else None,
            'exif_camera_model': self.exif_camera_model,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewed_by': self.reviewed_by,
            'url': url_for('static', filename='uploads/' + self.filename) if self.filename else None,
            'link_name': self.link.name if self.link else None,
        }
