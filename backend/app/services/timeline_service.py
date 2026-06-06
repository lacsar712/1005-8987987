from flask import url_for
from ..db import db, Album, Photo
from .photo_date_grouper import PhotoDateGrouper


class TimelineService:
    """时间线服务：获取公开相册照片并进行时间线聚合"""

    @staticmethod
    def get_public_albums():
        """获取所有公开可见的相册（排除仅管理员可见的相册）"""
        return Album.query.filter_by(is_admin_only=False).all()

    @staticmethod
    def get_public_album_ids():
        """获取所有公开相册的 ID 列表"""
        albums = TimelineService.get_public_albums()
        return [a.id for a in albums]

    @staticmethod
    def get_photos_for_timeline(album_ids=None, use_exif: bool = False):
        """
        获取时间线范围内的照片
        :param album_ids: 可选的相册 ID 过滤列表；None 表示全部公开相册
        :param use_exif: 是否按 EXIF 拍摄时间排序（否则按上传时间）
        :return: 照片列表
        """
        public_ids = TimelineService.get_public_album_ids()
        query = Photo.query.filter(Photo.album_id.in_(public_ids))

        if album_ids:
            filtered = [pid for pid in album_ids if pid in public_ids]
            if filtered:
                query = query.filter(Photo.album_id.in_(filtered))

        if use_exif:
            query = query.order_by(
                Photo.exif_taken_at.desc().nullslast(),
                Photo.uploaded_at.desc()
            )
        else:
            query = query.order_by(Photo.uploaded_at.desc())

        return query.all()

    @staticmethod
    def serialize_photo(photo) -> dict:
        """将照片对象序列化为前端可用的字典"""
        album = Album.query.get(photo.album_id)
        return {
            "photo_id": photo.id,
            "filename": photo.filename,
            "original_filename": photo.original_filename,
            "album_id": photo.album_id,
            "album_title": album.title if album else "",
            "uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
            "exif_taken_at": photo.exif_taken_at.isoformat() if photo.exif_taken_at else None,
            "url": url_for("static", filename="uploads/" + photo.filename)
        }

    @staticmethod
    def get_timeline_data(album_ids=None, use_exif: bool = False):
        """
        获取完整的时间线数据（已分组、已序列化）
        :return: dict: {
            "groups": {date_key: {"label", "photos": [serialized], "date_obj"}},
            "sorted_keys": [...],
            "years": [...],
            "albums": [{id, title, photo_count}],
            "total_photos": int
        }
        """
        photos = TimelineService.get_photos_for_timeline(album_ids, use_exif)
        groups_raw = PhotoDateGrouper.group_by_date(photos, use_exif)
        sorted_keys = PhotoDateGrouper.sort_group_keys(groups_raw, use_exif)
        years = PhotoDateGrouper.extract_years(groups_raw)

        groups = {}
        for key, data in groups_raw.items():
            groups[key] = {
                "label": data["label"],
                "photos": [TimelineService.serialize_photo(p) for p in data["photos"]],
                "year": str(data["date_obj"].year) if data["date_obj"] else None
            }

        all_albums = TimelineService.get_public_albums()
        albums_info = []
        for album in all_albums:
            photo_count = Photo.query.filter_by(album_id=album.id).count()
            albums_info.append({"id": album.id, "title": album.title, "photo_count": photo_count})

        return {
            "groups": groups,
            "sorted_keys": sorted_keys,
            "years": years,
            "albums": albums_info,
            "total_photos": len(photos)
        }
