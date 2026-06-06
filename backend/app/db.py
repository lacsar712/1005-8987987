import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
