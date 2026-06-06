from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Album(db.Model):
    """相册模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    photos = db.relationship('Photo', backref='album', lazy=True, cascade="all, delete-orphan")

class Photo(db.Model):
    """照片模型"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(100), nullable=False)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    highlights = db.relationship('Highlight', backref='photo', lazy=True, cascade="all, delete-orphan")

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
