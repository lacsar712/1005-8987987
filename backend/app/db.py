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
