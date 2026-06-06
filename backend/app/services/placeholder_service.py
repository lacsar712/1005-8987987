class PlaceholderService:
    """SVG 占位图生成服务：负责生成带 aspect-ratio 标记的占位图"""

    @staticmethod
    def generate_svg(aspect_ratio: float, label: str = "照片占位", color_scheme: str = "default") -> str:
        """
        生成带宽高比标记的 SVG 占位图
        :param aspect_ratio: 宽高比 (width/height)
        :param label: 占位图标签文字
        :param color_scheme: 配色方案
        :return: SVG 字符串
        """
        width = 800
        height = int(width / aspect_ratio) if aspect_ratio > 0 else 600

        colors = {
            "default": {"bg": "#f3f4f6", "border": "#d1d5db", "text": "#6b7280", "accent": "#9ca3af"},
            "travel": {"bg": "#ecfeff", "border": "#a5f3fc", "text": "#0e7490", "accent": "#06b6d4"},
            "food": {"bg": "#fff7ed", "border": "#fed7aa", "text": "#c2410c", "accent": "#f97316"},
            "family": {"bg": "#fdf2f8", "border": "#fbcfe8", "text": "#be185d", "accent": "#ec4899"},
            "product": {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#15803d", "accent": "#22c55e"},
            "blank": {"bg": "#f9fafb", "border": "#e5e7eb", "text": "#4b5563", "accent": "#6b7280"},
        }
        c = colors.get(color_scheme, colors["default"])

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">
  <defs>
    <pattern id="grid-{color_scheme}" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="{c['border']}" stroke-width="1" opacity="0.5"/>
    </pattern>
  </defs>
  <rect width="100%" height="100%" fill="{c['bg']}"/>
  <rect width="100%" height="100%" fill="url(#grid-{color_scheme})"/>
  <rect x="4" y="4" width="{width-8}" height="{height-8}" fill="none" stroke="{c['border']}" stroke-width="2" stroke-dasharray="8,4" rx="8"/>
  <g transform="translate({width//2}, {height//2})">
    <svg x="-48" y="-70" width="96" height="96" viewBox="0 0 24 24" fill="none" stroke="{c['accent']}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
    <text x="0" y="60" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="28" fill="{c['text']}" font-weight="600">{label}</text>
    <text x="0" y="100" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="22" fill="{c['accent']}" font-weight="500">aspect-ratio: {aspect_ratio:.2f}</text>
    <text x="0" y="136" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" font-size="18" fill="{c['text']}" opacity="0.7">{width} × {height}</text>
  </g>
</svg>'''
        return svg

    @staticmethod
    def get_preset_placeholders(template_slug: str) -> list:
        """
        获取指定模板的预设占位图配置 (3 张)
        :param template_slug: 模板标识
        :return: [{'aspect_ratio': float, 'label': str, 'color_scheme': str}, ...]
        """
        presets = {
            "travel": [
                {"aspect_ratio": 16 / 9, "label": "风景全景", "color_scheme": "travel"},
                {"aspect_ratio": 4 / 3, "label": "旅途留影", "color_scheme": "travel"},
                {"aspect_ratio": 3 / 4, "label": "人像竖拍", "color_scheme": "travel"},
            ],
            "food": [
                {"aspect_ratio": 1 / 1, "label": "美食特写", "color_scheme": "food"},
                {"aspect_ratio": 4 / 3, "label": "餐桌俯拍", "color_scheme": "food"},
                {"aspect_ratio": 16 / 9, "label": "餐厅环境", "color_scheme": "food"},
            ],
            "family": [
                {"aspect_ratio": 3 / 2, "label": "全家福", "color_scheme": "family"},
                {"aspect_ratio": 2 / 3, "label": "孩子成长", "color_scheme": "family"},
                {"aspect_ratio": 1 / 1, "label": "温馨瞬间", "color_scheme": "family"},
            ],
            "product": [
                {"aspect_ratio": 1 / 1, "label": "产品主图", "color_scheme": "product"},
                {"aspect_ratio": 4 / 5, "label": "细节展示", "color_scheme": "product"},
                {"aspect_ratio": 16 / 9, "label": "场景展示", "color_scheme": "product"},
            ],
            "blank": [
                {"aspect_ratio": 4 / 3, "label": "照片位 1", "color_scheme": "blank"},
                {"aspect_ratio": 1 / 1, "label": "照片位 2", "color_scheme": "blank"},
                {"aspect_ratio": 16 / 9, "label": "照片位 3", "color_scheme": "blank"},
            ],
        }
        return presets.get(template_slug, presets["blank"])

    @staticmethod
    def find_best_matching_placeholder(placeholders, photo_aspect_ratio: float):
        """
        按宽高比最接近原则，为照片找到最合适的占位槽位
        :param placeholders: PhotoPlaceholder 列表 (未被替换的)
        :param photo_aspect_ratio: 照片的宽高比
        :return: 最佳匹配的 PhotoPlaceholder 或 None
        """
        if not placeholders or photo_aspect_ratio is None:
            return None
        available = [p for p in placeholders if not p.is_replaced]
        if not available:
            return None
        best = None
        min_diff = float('inf')
        for p in available:
            diff = abs(p.aspect_ratio - photo_aspect_ratio)
            if diff < min_diff:
                min_diff = diff
                best = p
        return best
