from ..db import db, Template, Album, PhotoPlaceholder
from .placeholder_service import PlaceholderService


class TemplateSeeder:
    """内置模板数据初始化：负责五套内置模板的数据生成"""

    BUILTIN_TEMPLATES = [
        {
            "slug": "travel",
            "name": "旅行",
            "description": "记录旅途中的美好风景与回忆",
            "scene_description": "适用于旅行日志、户外探险、城市漫游、自然风光等摄影主题",
            "prefill_description": "用镜头记录旅途中的每一个精彩瞬间，把风景、故事和感动都留在这本相册里。",
            "suggested_tags": ["旅行", "风景", "户外", "城市", "自然", "打卡"],
            "layout_params": {
                "columns": 3,
                "gap": 16,
                "sort_rule": "created_desc",
                "layout_mode": "masonry",
                "border_radius": 8,
            },
            "color_scheme": "travel",
        },
        {
            "slug": "food",
            "name": "美食",
            "description": "记录舌尖上的美味与餐桌故事",
            "scene_description": "适用于美食探店、家庭烹饪、烘焙甜点、餐厅分享等主题",
            "prefill_description": "记录每一次味蕾的惊喜，把美味的瞬间和温暖的故事都收藏在这里。",
            "suggested_tags": ["美食", "探店", "烹饪", "烘焙", "下午茶", "餐厅"],
            "layout_params": {
                "columns": 2,
                "gap": 20,
                "sort_rule": "created_desc",
                "layout_mode": "grid",
                "border_radius": 12,
            },
            "color_scheme": "food",
        },
        {
            "slug": "family",
            "name": "家庭",
            "description": "珍藏家人的温馨时光与成长记忆",
            "scene_description": "适用于家庭聚会、孩子成长、节日团圆、亲子活动等主题",
            "prefill_description": "这是我们家的故事集，记录每一个平凡日子里的温馨与感动，见证孩子的成长和家人的陪伴。",
            "suggested_tags": ["家庭", "亲子", "成长", "节日", "团圆", "温馨"],
            "layout_params": {
                "columns": 2,
                "gap": 24,
                "sort_rule": "created_asc",
                "layout_mode": "masonry",
                "border_radius": 16,
            },
            "color_scheme": "family",
        },
        {
            "slug": "product",
            "name": "产品展示",
            "description": "专业的产品展示与作品集模板",
            "scene_description": "适用于产品展示、作品集、电商详情、设计案例等商业展示",
            "prefill_description": "专业展示产品的细节与特色，用清晰的视觉语言传达产品价值。",
            "suggested_tags": ["产品", "展示", "设计", "作品", "商业", "电商"],
            "layout_params": {
                "columns": 3,
                "gap": 12,
                "sort_rule": "custom",
                "layout_mode": "grid",
                "border_radius": 4,
            },
            "color_scheme": "product",
        },
        {
            "slug": "blank",
            "name": "空白",
            "description": "从零开始创建你自己的相册",
            "scene_description": "适用于任何自定义场景，不受预设风格限制",
            "prefill_description": "",
            "suggested_tags": [],
            "layout_params": {
                "columns": 4,
                "gap": 12,
                "sort_rule": "created_desc",
                "layout_mode": "masonry",
                "border_radius": 8,
            },
            "color_scheme": "blank",
        },
    ]

    @classmethod
    def seed_builtin_templates(cls):
        """初始化内置模板（仅当模板表为空时执行）"""
        if Template.query.count() > 0:
            return
        for tpl_data in cls.BUILTIN_TEMPLATES:
            template = Template(
                slug=tpl_data["slug"],
                name=tpl_data["name"],
                description=tpl_data["description"],
                scene_description=tpl_data["scene_description"],
                prefill_description=tpl_data["prefill_description"],
                is_builtin=True,
                is_active=True,
            )
            template.set_suggested_tags(tpl_data["suggested_tags"])
            template.set_layout_params(tpl_data["layout_params"])

            svgs = []
            presets = PlaceholderService.get_preset_placeholders(tpl_data["slug"])
            for p in presets:
                svg = PlaceholderService.generate_svg(
                    aspect_ratio=p["aspect_ratio"],
                    label=p["label"],
                    color_scheme=p["color_scheme"],
                )
                svgs.append({
                    "svg": svg,
                    "aspect_ratio": round(p["aspect_ratio"], 2),
                    "label": p["label"],
                })
            template.set_placeholder_svgs(svgs)
            template.cover_placeholder = svgs[0]["svg"] if svgs else ""

            db.session.add(template)
        db.session.commit()


class TemplateService:
    """模板 CRUD 服务：负责模板的增删改查与基础管理"""

    @staticmethod
    def get_all(active_only: bool = True):
        """获取所有模板"""
        query = Template.query
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(Template.is_builtin.desc(), Template.created_at.asc()).all()

    @staticmethod
    def get_by_id(template_id: int):
        """按 ID 获取模板"""
        return Template.query.get(template_id)

    @staticmethod
    def get_by_slug(slug: str):
        """按 slug 获取模板"""
        return Template.query.filter_by(slug=slug).first()

    @staticmethod
    def create(data: dict):
        """创建自定义模板"""
        template = Template(
            name=data.get("name", "未命名模板"),
            slug=data.get("slug", ""),
            description=data.get("description", ""),
            scene_description=data.get("scene_description", ""),
            prefill_description=data.get("prefill_description", ""),
            is_builtin=False,
            is_active=data.get("is_active", True),
        )
        template.set_suggested_tags(data.get("suggested_tags", []))
        template.set_layout_params(data.get("layout_params", {}))

        placeholder_svgs = data.get("placeholder_svgs") or []
        if not placeholder_svgs:
            layout_params = data.get("layout_params", {})
            color_scheme = "blank"
            presets = PlaceholderService.get_preset_placeholders(color_scheme)
            placeholder_svgs = []
            for p in presets:
                svg = PlaceholderService.generate_svg(
                    aspect_ratio=p["aspect_ratio"],
                    label=p["label"],
                    color_scheme=color_scheme,
                )
                placeholder_svgs.append({
                    "svg": svg,
                    "aspect_ratio": round(p["aspect_ratio"], 2),
                    "label": p["label"],
                })
        template.set_placeholder_svgs(placeholder_svgs)

        cover_placeholder = data.get("cover_placeholder")
        if not cover_placeholder and placeholder_svgs:
            cover_placeholder = placeholder_svgs[0]["svg"]
        template.cover_placeholder = cover_placeholder or ""

        db.session.add(template)
        db.session.commit()
        return template

    @staticmethod
    def update(template_id: int, data: dict):
        """更新模板"""
        template = Template.query.get_or_404(template_id)
        if "name" in data:
            template.name = data["name"]
        if "slug" in data:
            template.slug = data["slug"]
        if "description" in data:
            template.description = data["description"]
        if "scene_description" in data:
            template.scene_description = data["scene_description"]
        if "prefill_description" in data:
            template.prefill_description = data["prefill_description"]
        if "suggested_tags" in data:
            template.set_suggested_tags(data["suggested_tags"])
        if "layout_params" in data:
            template.set_layout_params(data["layout_params"])
        if "placeholder_svgs" in data:
            svgs = data["placeholder_svgs"]
            if svgs is not None and len(svgs) == 0 and len(template.get_placeholder_svgs()) == 0:
                presets = PlaceholderService.get_preset_placeholders("blank")
                gen_svgs = []
                for p in presets:
                    svg = PlaceholderService.generate_svg(
                        aspect_ratio=p["aspect_ratio"],
                        label=p["label"],
                        color_scheme="blank",
                    )
                    gen_svgs.append({
                        "svg": svg,
                        "aspect_ratio": round(p["aspect_ratio"], 2),
                        "label": p["label"],
                    })
                template.set_placeholder_svgs(gen_svgs)
            elif svgs is not None:
                template.set_placeholder_svgs(svgs)
        if "cover_placeholder" in data:
            if data["cover_placeholder"]:
                template.cover_placeholder = data["cover_placeholder"]
            elif not template.cover_placeholder:
                svgs = template.get_placeholder_svgs()
                if svgs:
                    template.cover_placeholder = svgs[0]["svg"]
        if "is_active" in data:
            template.is_active = data["is_active"]
        db.session.commit()
        return template

    @staticmethod
    def delete(template_id: int):
        """删除模板（内置模板不可删除）"""
        template = Template.query.get_or_404(template_id)
        if template.is_builtin:
            raise ValueError("内置模板不可删除")
        db.session.delete(template)
        db.session.commit()


class TemplateApplier:
    """模板应用服务：负责将模板应用到相册，预填内容并插入占位图"""

    @staticmethod
    def apply_template_to_album(album: Album, template: Template, override_title: bool = False):
        """
        将模板应用到相册
        :param album: 目标相册
        :param template: 要应用的模板
        :param override_title: 是否覆盖相册标题（默认不覆盖）
        """
        album.template_id = template.id

        if not album.description and template.prefill_description:
            album.description = template.prefill_description

        layout_params = template.get_layout_params()
        current_layout = album.get_layout_config()
        merged_layout = {**layout_params, **current_layout}
        album.set_layout_config(merged_layout)

        existing_tags = album.get_tags_list()
        suggested = template.get_suggested_tags()
        for tag in suggested:
            if tag not in existing_tags:
                existing_tags.append(tag)
        album.set_tags_list(existing_tags)

        TemplateApplier._insert_placeholders(album, template)

        db.session.commit()
        return album

    @staticmethod
    def _insert_placeholders(album: Album, template: Template):
        """向相册插入模板的 3 张 SVG 占位图"""
        svgs_data = template.get_placeholder_svgs()
        for idx, data in enumerate(svgs_data[:3]):
            placeholder = PhotoPlaceholder(
                album_id=album.id,
                svg_content=data.get("svg", ""),
                aspect_ratio=float(data.get("aspect_ratio", 1.0)),
                slot_index=idx,
                is_replaced=False,
            )
            db.session.add(placeholder)


class TemplateCombiner:
    """组合模板服务：允许将多个模板的内容包合并到一个新相册"""

    @staticmethod
    def combine_templates(template_ids: list, album_title: str) -> Album:
        """
        合并多个模板到新相册
        :param template_ids: 要合并的模板 ID 列表
        :param album_title: 新相册标题
        :return: 合并后的新相册
        """
        templates = [Template.query.get(tid) for tid in template_ids if Template.query.get(tid)]
        if not templates:
            raise ValueError("未找到有效的模板")

        merged_description_parts = []
        merged_tags = []
        merged_svgs = []
        layout_param_list = []

        for tpl in templates:
            if tpl.prefill_description and tpl.prefill_description not in merged_description_parts:
                merged_description_parts.append(tpl.prefill_description)

            for tag in tpl.get_suggested_tags():
                if tag not in merged_tags:
                    merged_tags.append(tag)

            for svg_data in tpl.get_placeholder_svgs():
                merged_svgs.append(svg_data)

            layout_param_list.append(tpl.get_layout_params())

        merged_description = "\n\n".join(merged_description_parts)
        merged_layout = TemplateCombiner._merge_layout_params(layout_param_list)

        album = Album(
            title=album_title,
            description=merged_description,
        )
        album.set_layout_config(merged_layout)
        album.set_tags_list(merged_tags)
        if templates:
            album.template_id = templates[0].id

        db.session.add(album)
        db.session.flush()

        for idx, svg_data in enumerate(merged_svgs[:9]):
            placeholder = PhotoPlaceholder(
                album_id=album.id,
                svg_content=svg_data.get("svg", ""),
                aspect_ratio=float(svg_data.get("aspect_ratio", 1.0)),
                slot_index=idx,
                is_replaced=False,
            )
            db.session.add(placeholder)

        db.session.commit()
        return album

    @staticmethod
    def _merge_layout_params(param_list: list) -> dict:
        """合并多个模板的布局参数（取第一个非空值为主，叠加特殊字段）"""
        if not param_list:
            return {"columns": 3, "gap": 16, "sort_rule": "created_desc", "layout_mode": "masonry", "border_radius": 8}
        merged = dict(param_list[0])
        for params in param_list[1:]:
            for k, v in params.items():
                if k not in merged or merged[k] is None:
                    merged[k] = v
        return merged
