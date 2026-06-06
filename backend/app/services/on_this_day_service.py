from datetime import datetime
from flask import url_for
from ..db import db, Album, Photo
from .timeline_service import TimelineService


class OnThisDayService:
    """历史上的今天服务：聚合历年同月同日上传/拍摄的照片"""

    @staticmethod
    def get_photos_on_this_day(use_exif: bool = False, limit_per_year: int = 5):
        """
        获取历年"今天"同月同日的照片，按年份分组
        :param use_exif: True 使用 EXIF 拍摄时间，False 使用上传时间
        :param limit_per_year: 每年最多返回的照片数量
        :return: list: [{"year": int, "photos": [serialized_photo, ...]}, ...]
        """
        today = datetime.now()
        month = today.month
        day = today.day

        public_ids = TimelineService.get_public_album_ids()
        query = Photo.query.filter(Photo.album_id.in_(public_ids))

        all_photos = query.all()
        year_groups = {}

        for photo in all_photos:
            if use_exif:
                dt = photo.exif_taken_at
            else:
                dt = photo.uploaded_at

            if not dt:
                continue

            if dt.month == month and dt.day == day and dt.year != today.year:
                year = dt.year
                if year not in year_groups:
                    year_groups[year] = []
                if len(year_groups[year]) < limit_per_year:
                    year_groups[year].append(photo)

        result = []
        for year in sorted(year_groups.keys(), reverse=True):
            result.append({
                "year": year,
                "photos": [TimelineService.serialize_photo(p) for p in year_groups[year]]
            })

        return result

    @staticmethod
    def has_any_photo(use_exif: bool = False) -> bool:
        """判断是否存在任何"历史上的今天"照片"""
        return len(OnThisDayService.get_photos_on_this_day(use_exif, limit_per_year=1)) > 0
