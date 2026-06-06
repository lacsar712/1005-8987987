from datetime import datetime, date
from collections import defaultdict


class PhotoDateGrouper:
    """照片日期分组器：将照片按日期分组，并生成友好的标签"""

    UNKNOWN_DATE_KEY = "unknown"

    @staticmethod
    def get_date_label(dt: datetime) -> str:
        """为给定日期生成用户友好的标签（今天、昨天、具体日期）"""
        if not dt:
            return "未知拍摄日期"
        today = date.today()
        photo_date = dt.date()
        delta = (today - photo_date).days
        if delta == 0:
            return "今天"
        elif delta == 1:
            return "昨天"
        else:
            return dt.strftime("%Y年%m月%d日")

    @staticmethod
    def get_date_key(dt: datetime) -> str:
        """获取用于分组排序的日期键"""
        if not dt:
            return PhotoDateGrouper.UNKNOWN_DATE_KEY
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def group_by_date(photos, use_exif: bool = False):
        """
        将照片列表按日期分组
        :param photos: 照片对象列表，需包含 uploaded_at 和可选的 exif_taken_at
        :param use_exif: 是否使用 EXIF 拍摄时间，否则使用上传时间
        :return: dict: {date_key: {"label": str, "photos": list, "date_obj": date|None}}
        """
        groups = defaultdict(lambda: {"label": "", "photos": [], "date_obj": None})

        for photo in photos:
            dt = photo.exif_taken_at if use_exif else photo.uploaded_at
            if use_exif and not photo.exif_taken_at:
                key = PhotoDateGrouper.UNKNOWN_DATE_KEY
                label = "未知拍摄日期"
                date_obj = None
            else:
                key = PhotoDateGrouper.get_date_key(dt)
                label = PhotoDateGrouper.get_date_label(dt)
                date_obj = dt.date()

            groups[key]["label"] = label
            groups[key]["date_obj"] = date_obj
            groups[key]["photos"].append(photo)

        return dict(groups)

    @staticmethod
    def sort_group_keys(groups: dict, use_exif: bool = False) -> list:
        """
        对分组键进行排序，日期倒序，未知日期排在最后
        :return: 排序后的 key 列表
        """
        unknown_key = PhotoDateGrouper.UNKNOWN_DATE_KEY
        dated_keys = [k for k in groups.keys() if k != unknown_key]
        dated_keys.sort(reverse=True)
        if unknown_key in groups:
            dated_keys.append(unknown_key)
        return dated_keys

    @staticmethod
    def extract_years(groups: dict) -> list:
        """
        从分组数据中提取所有涉及的年份（倒序排列）
        :return: list of str, e.g. ["2026", "2025", "2024"]
        """
        years = set()
        for key, data in groups.items():
            if key == PhotoDateGrouper.UNKNOWN_DATE_KEY:
                continue
            if data["date_obj"]:
                years.add(str(data["date_obj"].year))
        return sorted(years, reverse=True)
