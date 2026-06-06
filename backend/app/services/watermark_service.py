from datetime import datetime
from ..db import db, WatermarkConfig, AlbumWatermarkOverride, Album


class WatermarkConfigService:
    """全局水印配置 CRUD 与获取"""

    DEFAULT_CONFIG = {
        'enabled': False,
        'watermark_type': 'text',
        'text_content': '© 在线相册',
        'text_font_size': 32,
        'text_opacity': 0.6,
        'text_color': '#ffffff',
        'text_position': 'bottom-right',
        'text_tiling': False,
        'text_tiling_spacing': 150,
        'text_tiling_angle': -30,
        'text_stroke': True,
        'text_stroke_color': '#000000',
        'text_stroke_width': 2,
        'image_filename': '',
        'image_scale': 0.15,
        'image_opacity': 0.7,
        'image_position': 'bottom-right',
        'image_tiling': False,
        'image_tiling_spacing': 200,
        'image_tiling_angle': 0,
        'adaptive_contrast': True,
    }

    @classmethod
    def get_config(cls):
        """获取全局水印配置，不存在则创建默认"""
        config = WatermarkConfig.query.first()
        if not config:
            config = WatermarkConfig(**cls.DEFAULT_CONFIG)
            db.session.add(config)
            db.session.commit()
        return config

    @classmethod
    def update_config(cls, data):
        """更新全局水印配置"""
        config = cls.get_config()
        field_mapping = [
            'enabled', 'watermark_type',
            'text_content', 'text_font_size', 'text_opacity', 'text_color',
            'text_position', 'text_tiling', 'text_tiling_spacing', 'text_tiling_angle',
            'text_stroke', 'text_stroke_color', 'text_stroke_width',
            'image_filename', 'image_scale', 'image_opacity', 'image_position',
            'image_tiling', 'image_tiling_spacing', 'image_tiling_angle',
            'adaptive_contrast',
        ]
        for field in field_mapping:
            if field in data:
                setattr(config, field, data[field])
        db.session.commit()
        return config


class AlbumWatermarkService:
    """相册级水印覆盖配置管理"""

    @staticmethod
    def get_override(album_id):
        """获取相册水印覆盖配置"""
        return AlbumWatermarkOverride.query.filter_by(album_id=album_id).first()

    @staticmethod
    def list_overrides():
        """列出所有相册水印覆盖配置"""
        return AlbumWatermarkOverride.query.all()

    @staticmethod
    def set_override(album_id, data):
        """设置或更新相册水印覆盖配置"""
        override = AlbumWatermarkOverride.query.filter_by(album_id=album_id).first()
        if not override:
            override = AlbumWatermarkOverride(album_id=album_id)
            db.session.add(override)

        for field in ['enabled', 'override_text', 'override_position', 'text_content', 'text_position']:
            if field in data:
                setattr(override, field, data[field])

        db.session.commit()
        return override

    @staticmethod
    def remove_override(album_id):
        """删除相册水印覆盖配置"""
        override = AlbumWatermarkOverride.query.filter_by(album_id=album_id).first()
        if override:
            db.session.delete(override)
            db.session.commit()
            return True
        return False

    @staticmethod
    def resolve_effective_config(album_id):
        """
        解析相册的有效水印配置（合并全局 + 相册覆盖）
        :return: dict 包含 effective_text, effective_position, config(WatermarkConfig 对象克隆属性)
        """
        from copy import copy

        global_config = WatermarkConfigService.get_config()
        if not global_config.enabled:
            return None

        override = AlbumWatermarkOverride.query.filter_by(album_id=album_id).first()

        effective_text = global_config.text_content
        effective_position = (
            global_config.text_position
            if global_config.watermark_type == 'text'
            else global_config.image_position
        )
        is_enabled = global_config.enabled

        if override:
            if not override.enabled:
                return None
            if override.override_text and override.text_content:
                effective_text = override.text_content
            if override.override_position and override.text_position:
                effective_position = override.text_position

        return {
            'enabled': is_enabled,
            'watermark_type': global_config.watermark_type,
            'effective_text': effective_text,
            'effective_position': effective_position,
            'config': global_config,
        }

    @staticmethod
    def list_albums_with_overrides():
        """列出所有相册及其水印覆盖状态"""
        albums = Album.query.order_by(Album.created_at.desc()).all()
        overrides = {o.album_id: o for o in AlbumWatermarkOverride.query.all()}
        result = []
        for album in albums:
            override = overrides.get(album.id)
            result.append({
                'album_id': album.id,
                'album_title': album.title,
                'has_override': override is not None,
                'override': override.to_dict() if override else None,
            })
        return result
