import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO


class PositionCalculator:
    """九宫格位置与平铺坐标计算"""

    POSITIONS = [
        'top-left', 'top-center', 'top-right',
        'middle-left', 'center', 'middle-right',
        'bottom-left', 'bottom-center', 'bottom-right'
    ]

    @staticmethod
    def calculate_position(canvas_size, item_size, position, margin=20):
        """
        根据九宫格位置计算水印坐标
        :param canvas_size: (width, height) 画布尺寸
        :param item_size: (width, height) 水印尺寸
        :param position: 九宫格位置字符串
        :param margin: 边距（像素）
        :return: (x, y) 左上角坐标
        """
        cw, ch = canvas_size
        iw, ih = item_size
        margin = max(margin, 0)

        position_map = {
            'top-left': (margin, margin),
            'top-center': ((cw - iw) // 2, margin),
            'top-right': (cw - iw - margin, margin),
            'middle-left': (margin, (ch - ih) // 2),
            'center': ((cw - iw) // 2, (ch - ih) // 2),
            'middle-right': (cw - iw - margin, (ch - ih) // 2),
            'bottom-left': (margin, ch - ih - margin),
            'bottom-center': ((cw - iw) // 2, ch - ih - margin),
            'bottom-right': (cw - iw - margin, ch - ih - margin),
        }
        return position_map.get(position, position_map['bottom-right'])

    @staticmethod
    def generate_tiling_positions(canvas_size, item_size, spacing, angle=0):
        """
        生成平铺模式的所有水印坐标
        :param canvas_size: (width, height) 画布尺寸
        :param item_size: (width, height) 单个水印尺寸
        :param spacing: 水印间距（像素）
        :param angle: 旋转角度（度）
        :return: [(x, y, rotation_angle), ...] 坐标列表
        """
        cw, ch = canvas_size
        iw, ih = item_size
        diagonal = int(math.sqrt(iw ** 2 + ih ** 2))
        step = max(spacing + diagonal, diagonal + 20)

        positions = []
        for y in range(-diagonal, ch + diagonal, step):
            offset = 0 if (y // step) % 2 == 0 else step // 2
            for x in range(-diagonal + offset, cw + diagonal, step):
                positions.append((x, y, angle))
        return positions


class AdaptiveContrast:
    """自适应对比度算法：根据图片局部亮度自动切换水印颜色或描边"""

    BRIGHTNESS_THRESHOLD = 128

    @staticmethod
    def _hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb):
        return '#{:02x}{:02x}{:02x}'.format(*[max(0, min(255, int(c))) for c in rgb])

    @staticmethod
    def _invert_color(rgb):
        return (255 - rgb[0], 255 - rgb[1], 255 - rgb[2])

    @staticmethod
    def sample_local_brightness(image, bbox, sample_grid=5):
        """
        采样指定区域的平均亮度（0-255）
        :param image: PIL Image (已转灰度或RGB)
        :param bbox: (x1, y1, x2, y2) 采样区域
        :param sample_grid: 采样网格密度
        :return: 平均亮度值 0-255
        """
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.width, x2)
        y2 = min(image.height, y2)

        if x2 <= x1 or y2 <= y1:
            return 128

        region = image.crop((x1, y1, x2, y2)).convert('L')
        region = region.resize((sample_grid, sample_grid), Image.BILINEAR)
        pixels = list(region.getdata())
        if not pixels:
            return 128
        return sum(pixels) / len(pixels)

    @classmethod
    def resolve_text_colors(cls, image, position_bbox, base_color, use_stroke,
                            stroke_color, stroke_width):
        """
        根据局部亮度解析文字颜色和描边配置
        :return: dict with text_color, stroke_color, stroke_width, use_stroke
        """
        brightness = cls.sample_local_brightness(image, position_bbox)
        base_rgb = cls._hex_to_rgb(base_color)
        stroke_rgb = cls._hex_to_rgb(stroke_color)

        if brightness < cls.BRIGHTNESS_THRESHOLD:
            text_rgb = (255, 255, 255)
            resolved_stroke_rgb = (0, 0, 0)
        else:
            text_rgb = (0, 0, 0)
            resolved_stroke_rgb = (255, 255, 255)

        result = {
            'text_color': cls._rgb_to_hex(text_rgb),
            'stroke_color': cls._rgb_to_hex(resolved_stroke_rgb),
            'stroke_width': max(1, stroke_width),
            'use_stroke': True,
        }
        return result


class ExifPreserver:
    """EXIF 数据读取与写回工具"""

    @staticmethod
    def extract_exif(image):
        """从 PIL Image 中提取 EXIF 数据和原始 ICC Profile"""
        exif_bytes = b''
        icc_profile = None

        try:
            exif_bytes = image.info.get('exif', b'')
            if not exif_bytes and hasattr(image, '_getexif'):
                exif_info = image._getexif()
                if exif_info:
                    exif_bytes = image.info.get('exif', b'')
        except Exception:
            exif_bytes = b''

        try:
            icc_profile = image.info.get('icc_profile')
        except Exception:
            icc_profile = None

        return exif_bytes, icc_profile

    @staticmethod
    def save_with_exif(image, save_path, exif_bytes=b'', icc_profile=None, quality=95):
        """保存图片并保留 EXIF 和 ICC Profile"""
        ext = os.path.splitext(save_path)[1].lower()
        save_kwargs = {}

        if ext in ('.jpg', '.jpeg'):
            save_kwargs['quality'] = quality
            save_kwargs['subsampling'] = 'keep'
            if image.mode != 'RGB':
                image = image.convert('RGB')
        elif ext == '.png':
            save_kwargs['optimize'] = True
        elif ext == '.webp':
            save_kwargs['quality'] = quality

        if exif_bytes:
            save_kwargs['exif'] = exif_bytes
        if icc_profile:
            save_kwargs['icc_profile'] = icc_profile

        image.save(save_path, **save_kwargs)


class FontLoader:
    """字体加载器：支持系统字体回退"""

    _font_cache = {}

    CANDIDATE_FONTS = [
        'msyh.ttc', 'msyh.ttf', 'msyhbd.ttc',
        'simhei.ttf', 'simsun.ttc', 'simsun.ttf',
        'arial.ttf', 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf',
        'PingFang.ttc', 'Helvetica.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/PingFang.ttc',
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/simhei.ttf',
    ]

    @classmethod
    def load_font(cls, size):
        """加载可用字体，带缓存"""
        cache_key = size
        if cache_key in cls._font_cache:
            return cls._font_cache[cache_key]

        for font_path in cls.CANDIDATE_FONTS:
            try:
                font = ImageFont.truetype(font_path, size)
                cls._font_cache[cache_key] = font
                return font
            except (OSError, IOError):
                continue

        try:
            font = ImageFont.load_default()
            cls._font_cache[cache_key] = font
            return font
        except Exception:
            return None

    @classmethod
    def measure_text(cls, text, font):
        """测量文本尺寸"""
        if hasattr(font, 'getbbox'):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        elif hasattr(font, 'getsize'):
            return font.getsize(text)
        else:
            dummy = Image.new('RGB', (10, 10))
            draw = ImageDraw.Draw(dummy)
            return draw.textsize(text, font=font)


class TextWatermarkRenderer:
    """文字水印渲染器"""

    def __init__(self, processor):
        self.processor = processor

    def _render_single(self, draw, text, font, position, opacity, color,
                       use_stroke, stroke_color, stroke_width):
        """在指定位置绘制单个文字水印（含描边）"""
        x, y = position
        opacity_int = int(max(0, min(255, opacity * 255)))

        def hex_to_rgba(hex_c, alpha):
            rgb = AdaptiveContrast._hex_to_rgb(hex_c)
            return rgb + (alpha,)

        if use_stroke and stroke_width > 0:
            stroke_rgba = hex_to_rgba(stroke_color, opacity_int)
            sw = max(1, stroke_width)
            for dx in range(-sw, sw + 1):
                for dy in range(-sw, sw + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if dx * dx + dy * dy <= sw * sw:
                        draw.text((x + dx, y + dy), text, font=font, fill=stroke_rgba)

        text_rgba = hex_to_rgba(color, opacity_int)
        draw.text((x, y), text, font=font, fill=text_rgba)

    def render(self, base_image, config, effective_text, effective_position, adaptive_bbox=None):
        """
        渲染文字水印到图片
        :param base_image: PIL Image (RGBA)
        :param config: WatermarkConfig
        :param effective_text: 实际使用的水印文字
        :param effective_position: 实际使用的位置
        :param adaptive_bbox: 自适应采样区域（用于平铺时为整体区域）
        :return: 已合成水印的 RGBA 图像
        """
        overlay = Image.new('RGBA', base_image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = FontLoader.load_font(config.text_font_size)
        text_w, text_h = FontLoader.measure_text(effective_text, font)
        opacity = config.text_opacity

        if config.text_tiling:
            positions = PositionCalculator.generate_tiling_positions(
                base_image.size, (text_w, text_h),
                config.text_tiling_spacing,
                config.text_tiling_angle
            )
            for pos in positions:
                x, y, angle = pos
                if angle != 0:
                    tile = Image.new('RGBA', (text_w * 2, text_h * 2), (0, 0, 0, 0))
                    tile_draw = ImageDraw.Draw(tile)
                    self._render_single(
                        tile_draw, effective_text, font,
                        (text_w // 2, text_h // 2),
                        opacity, config.text_color,
                        config.text_stroke, config.text_stroke_color,
                        config.text_stroke_width
                    )
                    tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
                    overlay.alpha_composite(tile, (x - tile.width // 2, y - tile.height // 2))
                else:
                    self._render_single(
                        draw, effective_text, font, (x, y),
                        opacity, config.text_color,
                        config.text_stroke, config.text_stroke_color,
                        config.text_stroke_width
                    )
        else:
            position = PositionCalculator.calculate_position(
                base_image.size, (text_w, text_h), effective_position
            )

            resolved_colors = {
                'text_color': config.text_color,
                'stroke_color': config.text_stroke_color,
                'stroke_width': config.text_stroke_width,
                'use_stroke': config.text_stroke,
            }

            if config.adaptive_contrast:
                bbox = adaptive_bbox or (
                    position[0], position[1],
                    position[0] + text_w, position[1] + text_h
                )
                resolved_colors = AdaptiveContrast.resolve_text_colors(
                    base_image, bbox,
                    config.text_color, config.text_stroke,
                    config.text_stroke_color, config.text_stroke_width
                )

            self._render_single(
                draw, effective_text, font, position,
                opacity, resolved_colors['text_color'],
                resolved_colors['use_stroke'],
                resolved_colors['stroke_color'],
                resolved_colors['stroke_width']
            )

        return overlay


class ImageWatermarkRenderer:
    """PNG 图片水印渲染器"""

    def __init__(self, processor):
        self.processor = processor

    def _load_watermark_image(self, watermark_path, target_scale, base_size):
        """加载并缩放水印图片"""
        if not os.path.exists(watermark_path):
            return None

        wm_img = Image.open(watermark_path).convert('RGBA')
        base_w, base_h = base_size
        target_w = int(base_w * target_scale)
        if target_w <= 0:
            target_w = int(base_w * 0.1)
        ratio = target_w / wm_img.width
        target_h = int(wm_img.height * ratio)
        if target_h <= 0:
            target_h = 1
        wm_img = wm_img.resize((target_w, target_h), Image.LANCZOS)
        return wm_img

    def _apply_opacity(self, wm_img, opacity):
        """调整水印整体透明度"""
        if opacity >= 1.0:
            return wm_img
        alpha = wm_img.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        wm_img.putalpha(alpha)
        return wm_img

    def render(self, base_image, config, watermark_path, effective_position):
        """
        渲染图片水印到图像
        :param base_image: PIL Image (RGBA)
        :param config: WatermarkConfig
        :param watermark_path: 水印图片路径
        :param effective_position: 实际使用的位置
        :return: 已合成水印的 RGBA 图像
        """
        wm_img = self._load_watermark_image(watermark_path, config.image_scale, base_image.size)
        if wm_img is None:
            return Image.new('RGBA', base_image.size, (0, 0, 0, 0))

        wm_img = self._apply_opacity(wm_img, config.image_opacity)
        overlay = Image.new('RGBA', base_image.size, (0, 0, 0, 0))

        if config.image_tiling:
            positions = PositionCalculator.generate_tiling_positions(
                base_image.size, wm_img.size,
                config.image_tiling_spacing,
                config.image_tiling_angle
            )
            for pos in positions:
                x, y, angle = pos
                if angle != 0:
                    rotated = wm_img.rotate(angle, resample=Image.BICUBIC, expand=True)
                    overlay.alpha_composite(rotated, (x - rotated.width // 2, y - rotated.height // 2))
                else:
                    overlay.alpha_composite(wm_img, (x, y))
        else:
            position = PositionCalculator.calculate_position(
                base_image.size, wm_img.size, effective_position
            )
            overlay.alpha_composite(wm_img, position)

        return overlay


class WatermarkProcessor:
    """水印处理总控：整合文字/图片水印渲染、自适应对比度、EXIF 保留"""

    def __init__(self, uploads_folder, watermark_images_folder=None):
        self.uploads_folder = uploads_folder
        self.watermark_images_folder = watermark_images_folder or os.path.join(
            os.path.dirname(uploads_folder), 'watermarks'
        )
        os.makedirs(self.watermark_images_folder, exist_ok=True)
        self.text_renderer = TextWatermarkRenderer(self)
        self.image_renderer = ImageWatermarkRenderer(self)

    def _get_watermark_image_path(self, filename):
        if not filename:
            return None
        path = os.path.join(self.watermark_images_folder, filename)
        return path if os.path.exists(path) else None

    def process_image(self, image_path, config, effective_text=None,
                      effective_position=None, output_path=None):
        """
        对单张图片应用水印
        :param image_path: 原图路径
        :param config: WatermarkConfig 对象
        :param effective_text: 覆盖后的文字（None 则使用 config 中文字）
        :param effective_position: 覆盖后的位置（None 则使用 config 中位置）
        :param output_path: 输出路径（默认覆盖原图）
        :return: 成功与否
        """
        if not config.enabled:
            return False

        if not os.path.exists(image_path):
            return False

        output_path = output_path or image_path
        effective_text = effective_text or config.text_content
        effective_position = effective_position or (
            config.text_position if config.watermark_type == 'text' else config.image_position
        )

        try:
            with Image.open(image_path) as img:
                img = ImageOps.exif_transpose(img)
                exif_bytes, icc_profile = ExifPreserver.extract_exif(img)
                rgba = img.convert('RGBA')

                if config.watermark_type == 'text' and effective_text:
                    overlay = self.text_renderer.render(
                        rgba, config, effective_text, effective_position
                    )
                elif config.watermark_type == 'image':
                    wm_path = self._get_watermark_image_path(config.image_filename)
                    if wm_path:
                        overlay = self.image_renderer.render(
                            rgba, config, wm_path, effective_position
                        )
                    else:
                        overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
                else:
                    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))

                result = Image.alpha_composite(rgba, overlay)
                ExifPreserver.save_with_exif(
                    result, output_path, exif_bytes=exif_bytes, icc_profile=icc_profile
                )
                return True
        except Exception:
            return False

    def generate_preview(self, config, preview_width=800, preview_height=533,
                         effective_text=None, effective_position=None):
        """
        生成预览图（用于设置页实时展示）
        :return: BytesIO 对象（PNG 格式）
        """
        from PIL import ImageFilter

        gradient = Image.new('RGB', (preview_width, preview_height))
        pixels = gradient.load()
        for y in range(preview_height):
            for x in range(preview_width):
                r = int(255 * x / preview_width)
                g = int(180 * y / preview_height)
                b = int(120 + 80 * (1 - abs(x / preview_width - 0.5) * 2))
                pixels[x, y] = (r, g, b)

        for i in range(5):
            cx = (i + 1) * preview_width // 6
            cy = preview_height // 2 + ((-1) ** i) * 80
            radius = 60 + i * 10
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        px, py = cx + dx, cy + dy
                        if 0 <= px < preview_width and 0 <= py < preview_height:
                            shade = 30 + (i % 2) * 200
                            pixels[px, py] = (shade, shade, shade)

        blurred = gradient.filter(ImageFilter.GaussianBlur(radius=2))
        rgba = blurred.convert('RGBA')

        effective_text = effective_text or config.text_content
        effective_position = effective_position or (
            config.text_position if config.watermark_type == 'text' else config.image_position
        )

        if config.watermark_type == 'text' and effective_text:
            overlay = self.text_renderer.render(
                rgba, config, effective_text, effective_position
            )
        elif config.watermark_type == 'image':
            wm_path = self._get_watermark_image_path(config.image_filename)
            if wm_path:
                overlay = self.image_renderer.render(
                    rgba, config, wm_path, effective_position
                )
            else:
                overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
        else:
            overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))

        result = Image.alpha_composite(rgba, overlay)
        buffer = BytesIO()
        result.convert('RGB').save(buffer, format='JPEG', quality=90)
        buffer.seek(0)
        return buffer
