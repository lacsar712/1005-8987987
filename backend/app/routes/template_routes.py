from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, abort
from flask_login import login_required
from ..db import db, Template, Album, Photo, PhotoPlaceholder
from ..services import TemplateService, TemplateApplier, TemplateCombiner, PlaceholderService

templates_bp = Blueprint('templates', __name__)


@templates_bp.route('/api/templates')
def api_list_templates():
    """获取所有模板列表（JSON）"""
    active_only = request.args.get('active', '1') == '1'
    templates = TemplateService.get_all(active_only=active_only)
    return jsonify({
        'templates': [t.to_dict() for t in templates]
    })


@templates_bp.route('/api/templates/<int:template_id>')
def api_get_template(template_id):
    """获取单个模板详情（JSON）"""
    template = TemplateService.get_by_id(template_id)
    if not template:
        return jsonify({'success': False, 'message': '模板不存在'}), 404
    data = template.to_dict()
    data['placeholders'] = template.get_placeholder_svgs()
    return jsonify({'template': data})


@templates_bp.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    """创建自定义模板"""
    data = request.get_json() or {}
    try:
        template = TemplateService.create(data)
        return jsonify({'success': True, 'template': template.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@templates_bp.route('/api/templates/<int:template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """更新模板"""
    data = request.get_json() or {}
    try:
        template = TemplateService.update(template_id, data)
        return jsonify({'success': True, 'template': template.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@templates_bp.route('/api/templates/<int:template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """删除模板"""
    try:
        TemplateService.delete(template_id)
        return jsonify({'success': True, 'message': '模板已删除'})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@templates_bp.route('/api/templates/combine', methods=['POST'])
@login_required
def api_combine_templates():
    """组合多个模板创建新相册"""
    data = request.get_json() or {}
    template_ids = data.get('template_ids', [])
    title = data.get('title', '组合相册')
    if not template_ids or len(template_ids) < 2:
        return jsonify({'success': False, 'message': '请至少选择两个模板进行组合'}), 400
    try:
        album = TemplateCombiner.combine_templates(template_ids, title)
        return jsonify({'success': True, 'album_id': album.id, 'message': '组合相册创建成功'})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@templates_bp.route('/api/albums/<int:album_id>/placeholders')
def api_album_placeholders(album_id):
    """获取相册的占位图列表"""
    album = Album.query.get_or_404(album_id)
    placeholders = PhotoPlaceholder.query.filter_by(album_id=album_id).order_by(PhotoPlaceholder.slot_index.asc()).all()
    result = []
    for p in placeholders:
        result.append({
            'id': p.id,
            'album_id': p.album_id,
            'svg_content': p.svg_content,
            'aspect_ratio': p.aspect_ratio,
            'slot_index': p.slot_index,
            'is_replaced': p.is_replaced,
            'replaced_photo_id': p.replaced_photo.id if p.replaced_photo else None,
        })
    return jsonify({'placeholders': result})


@templates_bp.route('/api/albums/<int:album_id>/placeholders/suggest', methods=['POST'])
@login_required
def api_suggest_placeholder(album_id):
    """根据照片宽高比建议最佳匹配的占位槽位"""
    album = Album.query.get_or_404(album_id)
    data = request.get_json() or {}
    photo_aspect_ratio = data.get('aspect_ratio')
    if photo_aspect_ratio is None:
        return jsonify({'success': False, 'message': '缺少宽高比参数'}), 400
    placeholders = PhotoPlaceholder.query.filter_by(album_id=album_id).all()
    best = PlaceholderService.find_best_matching_placeholder(placeholders, float(photo_aspect_ratio))
    if best:
        return jsonify({
            'success': True,
            'placeholder': {
                'id': best.id,
                'aspect_ratio': best.aspect_ratio,
                'slot_index': best.slot_index,
            }
        })
    return jsonify({'success': False, 'message': '没有可用的占位槽位'})


@templates_bp.route('/templates')
@login_required
def template_management():
    """模板管理页面"""
    templates = TemplateService.get_all(active_only=False)
    return render_template('template_management.html', templates=templates)


@templates_bp.route('/album/create/with-template')
@login_required
def create_album_with_template():
    """带模板选择的相册创建页面"""
    templates = TemplateService.get_all(active_only=True)
    return render_template('create_album_with_template.html', templates=templates)
