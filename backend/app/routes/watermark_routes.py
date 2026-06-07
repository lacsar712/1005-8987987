import os
import uuid
import traceback
from flask import Blueprint, request, jsonify, render_template, send_file, send_from_directory, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename
from ..db import Album, WatermarkConfig
from ..services import (
    WatermarkConfigService, AlbumWatermarkService,
    WatermarkBatchProcessor, WatermarkProcessor
)

watermark_bp = Blueprint('watermark', __name__, url_prefix='/watermark')

ALLOWED_WATERMARK_EXTENSIONS = {'png'}

_batch_processor_singleton = None


def _get_watermarks_dir():
    uploads_dir = current_app.config['UPLOAD_FOLDER']
    return os.path.join(os.path.dirname(uploads_dir), 'watermarks')


def _get_batch_processor():
    global _batch_processor_singleton
    if _batch_processor_singleton is None:
        _batch_processor_singleton = WatermarkBatchProcessor.get_instance(
            uploads_folder=current_app.config['UPLOAD_FOLDER'],
            flask_app=current_app._get_current_object(),
        )
    return _batch_processor_singleton


def _get_processor():
    uploads = current_app.config['UPLOAD_FOLDER']
    return WatermarkProcessor(uploads)


def _allowed_watermark_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_WATERMARK_EXTENSIONS


@watermark_bp.route('/settings')
@login_required
def watermark_settings_page():
    """水印设置页面"""
    albums = Album.query.order_by(Album.created_at.desc()).all()
    return render_template('watermark_settings.html', albums=albums)


@watermark_bp.route('/api/config', methods=['GET'])
def api_get_config():
    """获取全局水印配置"""
    config = WatermarkConfigService.get_config()
    return jsonify({'config': config.to_dict()})


@watermark_bp.route('/api/config', methods=['POST'])
@login_required
def api_update_config():
    """更新全局水印配置"""
    data = request.get_json() or {}
    config = WatermarkConfigService.update_config(data)
    return jsonify({'success': True, 'config': config.to_dict()})


@watermark_bp.route('/static/watermarks/<path:filename>')
def serve_watermark_image(filename):
    """提供水印图片静态访问"""
    try:
        return send_from_directory(_get_watermarks_dir(), filename)
    except Exception:
        return ('', 404)


@watermark_bp.route('/api/preview', methods=['GET', 'POST'])
def api_generate_preview():
    """根据当前参数生成预览图"""
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
        else:
            data = {}

        config = WatermarkConfigService.get_config()
        temp_config = WatermarkConfig()
        for key, value in config.to_dict().items():
            if hasattr(temp_config, key):
                setattr(temp_config, key, value)

        boolean_fields = {'text_tiling', 'text_stroke', 'image_tiling', 'adaptive_contrast'}
        float_fields = {'text_opacity', 'image_opacity', 'image_scale'}
        int_fields = {'text_font_size', 'text_tiling_spacing', 'text_tiling_angle',
                      'text_stroke_width', 'image_tiling_spacing', 'image_tiling_angle'}

        for field in [
            'watermark_type', 'text_content', 'text_font_size', 'text_opacity',
            'text_color', 'text_position', 'text_tiling', 'text_tiling_spacing',
            'text_tiling_angle', 'text_stroke', 'text_stroke_color', 'text_stroke_width',
            'image_scale', 'image_opacity', 'image_position', 'image_tiling',
            'image_tiling_spacing', 'image_tiling_angle', 'adaptive_contrast'
        ]:
            if field in data:
                if field in boolean_fields:
                    setattr(temp_config, field, bool(data[field]))
                elif field in float_fields:
                    try:
                        setattr(temp_config, field, float(data[field]))
                    except (ValueError, TypeError):
                        pass
                elif field in int_fields:
                    try:
                        setattr(temp_config, field, int(data[field]))
                    except (ValueError, TypeError):
                        pass
                else:
                    setattr(temp_config, field, data[field])

        temp_config.enabled = True
        processor = _get_processor()
        eff_text = data.get('text_content') if data.get('text_content') else None
        eff_pos = data.get('text_position') or data.get('image_position') or None
        buffer = processor.generate_preview(
            temp_config,
            effective_text=eff_text,
            effective_position=eff_pos,
        )
        return send_file(buffer, mimetype='image/jpeg', cache_timeout=0)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@watermark_bp.route('/api/image/upload', methods=['POST'])
@login_required
def api_upload_watermark_image():
    """上传 PNG 水印图片"""
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': '未选择文件'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400

    if not _allowed_watermark_file(file.filename):
        return jsonify({'success': False, 'message': '仅支持 PNG 格式'}), 400

    uploads_dir = current_app.config['UPLOAD_FOLDER']
    watermarks_dir = os.path.join(os.path.dirname(uploads_dir), 'watermarks')
    os.makedirs(watermarks_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'png'
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(watermarks_dir, unique_name)
    file.save(save_path)

    config = WatermarkConfigService.update_config({'image_filename': unique_name})
    return jsonify({
        'success': True,
        'message': '水印图片已上传',
        'image_filename': unique_name,
        'config': config.to_dict(),
    })


@watermark_bp.route('/api/image/delete', methods=['POST'])
@login_required
def api_delete_watermark_image():
    """删除当前水印图片"""
    config = WatermarkConfigService.get_config()
    if config.image_filename:
        uploads_dir = current_app.config['UPLOAD_FOLDER']
        watermarks_dir = os.path.join(os.path.dirname(uploads_dir), 'watermarks')
        path = os.path.join(watermarks_dir, config.image_filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    WatermarkConfigService.update_config({'image_filename': ''})
    return jsonify({'success': True, 'message': '水印图片已删除'})


@watermark_bp.route('/api/overrides', methods=['GET'])
@login_required
def api_list_overrides():
    """列出所有相册水印覆盖配置"""
    result = AlbumWatermarkService.list_albums_with_overrides()
    return jsonify({'albums': result})


@watermark_bp.route('/api/overrides/<int:album_id>', methods=['GET'])
@login_required
def api_get_override(album_id):
    """获取单个相册的水印覆盖配置"""
    override = AlbumWatermarkService.get_override(album_id)
    return jsonify({
        'override': override.to_dict() if override else None,
    })


@watermark_bp.route('/api/overrides/<int:album_id>', methods=['POST'])
@login_required
def api_set_override(album_id):
    """设置相册水印覆盖配置"""
    data = request.get_json() or {}
    override = AlbumWatermarkService.set_override(album_id, data)
    return jsonify({'success': True, 'override': override.to_dict()})


@watermark_bp.route('/api/overrides/<int:album_id>', methods=['DELETE'])
@login_required
def api_remove_override(album_id):
    """删除相册水印覆盖配置"""
    AlbumWatermarkService.remove_override(album_id)
    return jsonify({'success': True, 'message': '已删除覆盖配置'})


@watermark_bp.route('/api/batch/status', methods=['GET'])
@login_required
def api_batch_status():
    """获取批量补打任务状态"""
    try:
        processor = _get_batch_processor()
        if processor is None:
            return jsonify({'task': None, 'is_running': False})
        task = processor.get_latest_task()
        running = processor.is_running()
        return jsonify({
            'task': task.to_dict() if task else None,
            'is_running': running,
        })
    except Exception as e:
        return jsonify({'task': None, 'is_running': False, 'error': str(e)})


@watermark_bp.route('/api/batch/start', methods=['POST'])
@login_required
def api_start_batch():
    """启动批量补打任务"""
    try:
        global_config = WatermarkConfigService.get_config()
        if not global_config.enabled:
            return jsonify({
                'success': False,
                'message': '全局水印开关未开启，请先启用水印再批量补打',
                'code': 'watermark_disabled'
            }), 400

        processor = _get_batch_processor()
        if processor is None:
            return jsonify({
                'success': False,
                'message': '任务处理器初始化失败，请刷新页面重试'
            }), 500

        if processor.is_running():
            return jsonify({
                'success': False,
                'message': '已有任务正在运行，请等待完成'
            }), 400

        data = request.get_json(silent=True) or {}
        album_id = data.get('album_id')
        if album_id is not None:
            try:
                album_id = int(album_id)
            except (ValueError, TypeError):
                album_id = None

        task = processor.start_task(album_id=album_id)
        if task:
            return jsonify({'success': True, 'task': task.to_dict()})
        else:
            if not processor.is_running():
                return jsonify({
                    'success': False,
                    'message': '没有可处理的照片，请先上传照片'
                }), 400
            return jsonify({
                'success': False,
                'message': '任务启动失败，请稍后重试'
            }), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'任务启动失败：{str(e)}'
        }), 500
