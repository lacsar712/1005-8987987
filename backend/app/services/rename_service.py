import re
import os
from datetime import datetime
from ..db import db, Photo, Album, RenameHistory


class RenameRuleEngine:
    """
    批量重命名规则引擎

    支持的规则：
    - 固定前缀/后缀
    - 序号补零（{index:03d} 类似 strftime 格式）
    - 正则表达式从 original_filename 提取 capture group（{regex:1} 引用第1组）
    - EXIF 拍摄日期占位符：{date:YYYY-MM-DD} 格式由用户指定
    - 相机型号占位符：{camera}
    - 原始文件名（不含扩展名）：{name}
    - 原始扩展名：{ext}
    """

    @staticmethod
    def _split_name_ext(filename):
        name, ext = os.path.splitext(filename)
        return name, ext.lstrip('.')

    @staticmethod
    def _apply_date_format(dt, fmt):
        """将用户格式（YYYY-MM-DD）转换为 strftime 并格式化"""
        if not dt:
            return ''
        fmt_map = {
            'YYYY': '%Y',
            'MM': '%m',
            'DD': '%d',
            'HH': '%H',
            'mm': '%M',
            'SS': '%S',
        }
        strftime_fmt = fmt
        for k, v in fmt_map.items():
            strftime_fmt = strftime_fmt.replace(k, v)
        try:
            return dt.strftime(strftime_fmt)
        except (ValueError, TypeError):
            return ''

    @classmethod
    def generate_new_name(cls, photo, template, index, zero_pad=3, regex_pattern=None, regex_groups=None):
        """
        根据规则模板生成新文件名（不含扩展名）

        :param photo: Photo 对象
        :param template: 用户配置的模板字符串，如 "Trip_{date:YYYY-MM-DD}_{index}_{name}"
        :param index: 当前序号（从1开始）
        :param zero_pad: 序号补零位数
        :param regex_pattern: 用户提供的正则表达式（可选），用于从原始文件名提取
        :param regex_groups: 预编译的 regex match groups（可选，为了预览时复用）
        :return: 新的文件名（不含扩展名）
        """
        orig_name, ext = cls._split_name_ext(photo.original_filename)

        result = template

        # 1. 处理 {index} / {index:N}
        def replace_index(match):
            pad_spec = match.group(1)
            if pad_spec:
                try:
                    pad = int(pad_spec)
                    return str(index).zfill(pad)
                except ValueError:
                    return str(index).zfill(zero_pad)
            return str(index).zfill(zero_pad)

        result = re.sub(r'\{index(?::(\d+))?\}', replace_index, result)

        # 2. 处理 {name} 原始文件名（不含扩展名）
        result = result.replace('{name}', orig_name)

        # 3. 处理 {ext} 原始扩展名
        result = result.replace('{ext}', ext)

        # 4. 处理 {date:FORMAT}
        def replace_date(match):
            fmt = match.group(1) or 'YYYY-MM-DD'
            dt = photo.exif_taken_at or photo.uploaded_at
            return cls._apply_date_format(dt, fmt)

        result = re.sub(r'\{date(?::([^}]+))?\}', replace_date, result)

        # 5. 处理 {camera}
        camera = photo.exif_camera_model or ''
        # 清理文件名非法字符
        camera = re.sub(r'[\\/:*?"<>|]', '_', camera)
        result = result.replace('{camera}', camera)

        # 6. 处理 {regex:N} / {regex}
        if regex_pattern:
            try:
                if regex_groups is None:
                    m = re.search(regex_pattern, photo.original_filename)
                    regex_groups = m.groups() if m else ()

                def replace_regex(match):
                    idx_str = match.group(1)
                    if idx_str:
                        try:
                            idx = int(idx_str)
                            if 1 <= idx <= len(regex_groups):
                                val = regex_groups[idx - 1] or ''
                                return re.sub(r'[\\/:*?"<>|]', '_', val)
                        except (ValueError, TypeError):
                            pass
                    # 默认返回第1组或空
                    if len(regex_groups) >= 1:
                        val = regex_groups[0] or ''
                        return re.sub(r'[\\/:*?"<>|]', '_', val)
                    return ''

                result = re.sub(r'\{regex(?::(\d+))?\}', replace_regex, result)
            except re.error:
                pass

        # 清理文件名非法字符（保留扩展名分隔由调用方处理）
        result = re.sub(r'[\\/:*?"<>|]', '_', result)
        # 清理首尾空白和点
        result = result.strip(' .')

        return result if result else orig_name

    @classmethod
    def preview(cls, photos, rules):
        """
        生成完整预览 diff 列表

        :param photos: Photo 对象列表
        :param rules: dict with keys:
            - template: str 模板
            - prefix: str (deprecated, 合并到 template)
            - suffix: str
            - zero_pad: int
            - start_index: int
            - regex_pattern: str
            - sort_by: str ('uploaded_at' | 'original_filename' | 'exif_taken_at')
            - sort_order: str ('asc' | 'desc')
        :return: list of dict: {photo_id, old_name, new_name, thumbnail, exif_info}
        """
        template = rules.get('template', '{name}')
        prefix = rules.get('prefix', '') or ''
        suffix = rules.get('suffix', '') or ''
        zero_pad = int(rules.get('zero_pad', 3) or 3)
        start_index = int(rules.get('start_index', 1) or 1)
        regex_pattern = rules.get('regex_pattern') or None
        sort_by = rules.get('sort_by', 'uploaded_at')
        sort_order = rules.get('sort_order', 'asc')

        # 组合完整模板（向后兼容 prefix/suffix 字段）
        if prefix or suffix:
            if template == '{name}' or not template:
                full_template = f'{prefix}{{name}}{suffix}'
            else:
                full_template = f'{prefix}{template}{suffix}'
        else:
            full_template = template or '{name}'

        # 排序
        def sort_key(p):
            if sort_by == 'original_filename':
                return p.original_filename.lower()
            elif sort_by == 'exif_taken_at':
                return (p.exif_taken_at or p.uploaded_at or datetime.min)
            else:
                return p.uploaded_at or datetime.min

        sorted_photos = sorted(photos, key=sort_key, reverse=(sort_order == 'desc'))

        # 预计算 regex groups（为了一致性）
        precomputed_regex = {}
        if regex_pattern:
            try:
                for p in sorted_photos:
                    m = re.search(regex_pattern, p.original_filename)
                    precomputed_regex[p.id] = m.groups() if m else ()
            except re.error:
                precomputed_regex = {}
                regex_pattern = None

        preview_items = []
        for idx, photo in enumerate(sorted_photos):
            current_index = start_index + idx
            regex_groups = precomputed_regex.get(photo.id)
            new_name_no_ext = cls.generate_new_name(
                photo, full_template, current_index, zero_pad, regex_pattern, regex_groups
            )
            _, ext = cls._split_name_ext(photo.original_filename)
            if ext:
                new_name = f'{new_name_no_ext}.{ext}'
            else:
                new_name = new_name_no_ext

            exif_date = ''
            if photo.exif_taken_at:
                exif_date = photo.exif_taken_at.strftime('%Y-%m-%d %H:%M:%S')
            elif photo.uploaded_at:
                exif_date = photo.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')

            preview_items.append({
                'photo_id': photo.id,
                'old_name': photo.original_filename,
                'new_name': new_name,
                'changed': new_name != photo.original_filename,
                'exif_date': exif_date,
                'exif_camera': photo.exif_camera_model or '',
            })

        return preview_items

    @classmethod
    def execute(cls, album_id, photo_ids, rules, excluded_ids=None):
        """
        执行批量重命名，保存 undo 快照

        :param album_id: 相册 ID
        :param photo_ids: 选中的照片 ID 列表
        :param rules: 规则 dict（同 preview）
        :param excluded_ids: 预览中手动排除的 photo_id 集合
        :return: (success_count, history_id, error)
        """
        excluded_ids = set(excluded_ids or [])
        photos = Photo.query.filter(
            Photo.album_id == album_id,
            Photo.id.in_(photo_ids)
        ).all()

        if not photos:
            return 0, None, '没有找到可重命名的照片'

        # 生成预览用于构建快照
        preview_items = cls.preview(photos, rules)
        preview_map = {item['photo_id']: item for item in preview_items}

        # 构建快照（用于 undo）
        snapshot = []
        applied_count = 0
        renamed_photos = []

        for photo in photos:
            if photo.id in excluded_ids:
                continue
            item = preview_map.get(photo.id)
            if not item or not item['changed']:
                continue

            snapshot.append({
                'photo_id': photo.id,
                'old_name': photo.original_filename,
                'new_name': item['new_name'],
            })

            photo.original_filename = item['new_name']
            renamed_photos.append(photo)
            applied_count += 1

        if applied_count == 0:
            return 0, None, '没有需要重命名的照片（可能已被全部排除或名称未变）'

        # 检测重复新名称（同相册内）
        all_new_names = [p.original_filename for p in renamed_photos]
        if len(set(all_new_names)) != len(all_new_names):
            db.session.rollback()
            return 0, None, '检测到重名，请调整规则后重试'

        # 保存历史记录
        rule_desc = cls._describe_rules(rules)
        history = RenameHistory(
            album_id=album_id,
            rule_description=rule_desc,
            photo_count=applied_count,
            is_applied=True,
        )
        history.set_snapshot_data(snapshot)
        db.session.add(history)

        try:
            db.session.commit()
            return applied_count, history.id, None
        except Exception as e:
            db.session.rollback()
            return 0, None, f'保存失败: {str(e)}'

    @staticmethod
    def _describe_rules(rules):
        """生成规则的人类可读描述"""
        parts = []
        if rules.get('prefix'):
            parts.append(f'前缀="{rules["prefix"]}"')
        if rules.get('suffix'):
            parts.append(f'后缀="{rules["suffix"]}"')
        if rules.get('template') and rules['template'] != '{name}':
            parts.append(f'模板="{rules["template"]}"')
        if rules.get('regex_pattern'):
            parts.append(f'正则=/{rules["regex_pattern"]}/')
        pad = rules.get('zero_pad', 3)
        start = rules.get('start_index', 1)
        parts.append(f'序号={start}起,{pad}位补零')
        sort_map = {
            'uploaded_at': '上传时间',
            'original_filename': '文件名',
            'exif_taken_at': '拍摄时间',
        }
        sort_by = rules.get('sort_by', 'uploaded_at')
        sort_order = rules.get('sort_order', 'asc')
        parts.append(f'排序={sort_map.get(sort_by, sort_by)}({"降序" if sort_order == "desc" else "升序"})')
        return '; '.join(parts)


class RenameHistoryService:
    """重命名历史管理服务"""

    @staticmethod
    def list_history(album_id=None, limit=50):
        q = RenameHistory.query
        if album_id:
            q = q.filter_by(album_id=album_id)
        return q.order_by(RenameHistory.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_latest(album_id=None):
        q = RenameHistory.query.filter_by(is_applied=True)
        if album_id:
            q = q.filter_by(album_id=album_id)
        return q.order_by(RenameHistory.created_at.desc()).first()

    @staticmethod
    def rollback(history_id):
        """回滚指定的重命名操作"""
        history = RenameHistory.query.get(history_id)
        if not history:
            return False, '记录不存在'
        if not history.is_applied:
            return False, '该操作已回滚'

        snapshot = history.get_snapshot_data()
        if not snapshot:
            return False, '快照数据损坏'

        restored = 0
        for item in snapshot:
            photo = Photo.query.get(item['photo_id'])
            if photo and photo.original_filename == item['new_name']:
                photo.original_filename = item['old_name']
                restored += 1

        history.is_applied = False
        history.rolled_back_at = datetime.utcnow()

        try:
            db.session.commit()
            return restored, None
        except Exception as e:
            db.session.rollback()
            return 0, f'回滚失败: {str(e)}'
