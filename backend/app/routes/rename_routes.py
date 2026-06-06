import re
from flask import Blueprint, request, jsonify, render_template, current_app, url_for
from flask_login import login_required
from ..db import db, Photo, Album
from ..services import RenameRuleEngine, RenameHistoryService

rename_bp = Blueprint('rename', __name__, url_prefix='/rename')


@rename_bp.route('/history')
@login_required
def rename_history_page():
    """重命名历史页面"""
    albums = Album.query.order_by(Album.created_at.desc()).all()
    return render_template('rename_history.html', albums=albums)


@rename_bp.route('/api/preview', methods=['POST'])
@login_required
def api_preview():
    """生成重命名预览"""
    data = request.get_json() or {}
    album_id = data.get('album_id')
    photo_ids = data.get('photo_ids') or []
    rules = data.get('rules') or {}

    if not album_id:
        return jsonify({'success': False, 'message': '缺少 album_id'}), 400

    album = Album.query.get(album_id)
    if not album:
        return jsonify({'success': False, 'message': '相册不存在'}), 404

    if not photo_ids:
        photos = album.photos
    else:
        photos = Photo.query.filter(
            Photo.album_id == album_id,
            Photo.id.in_([int(pid) for pid in photo_ids if str(pid).isdigit()])
        ).all()

    if not photos:
        return jsonify({'success': False, 'message': '没有选中的照片'}), 400

    try:
        preview_items = RenameRuleEngine.preview(photos, rules)
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成预览失败: {str(e)}'}), 500

    # 附加缩略图 URL
    for item in preview_items:
        photo = next((p for p in photos if p.id == item['photo_id']), None)
        if photo:
            item['thumbnail'] = url_for('static', filename='uploads/' + photo.filename)

    changed_count = sum(1 for i in preview_items if i['changed'])
    return jsonify({
        'success': True,
        'preview': preview_items,
        'total': len(preview_items),
        'changed_count': changed_count,
    })


@rename_bp.route('/api/execute', methods=['POST'])
@login_required
def api_execute():
    """执行批量重命名"""
    data = request.get_json() or {}
    album_id = data.get('album_id')
    photo_ids = data.get('photo_ids') or []
    rules = data.get('rules') or {}
    excluded_ids = data.get('excluded_ids') or []

    if not album_id:
        return jsonify({'success': False, 'message': '缺少 album_id'}), 400

    album = Album.query.get(album_id)
    if not album:
        return jsonify({'success': False, 'message': '相册不存在'}), 404

    if not photo_ids:
        return jsonify({'success': False, 'message': '没有选中的照片'}), 400

    clean_ids = [int(pid) for pid in photo_ids if str(pid).isdigit()]
    clean_excluded = [int(pid) for pid in excluded_ids if str(pid).isdigit()]

    # 校验正则
    if rules.get('regex_pattern'):
        try:
            re.compile(rules['regex_pattern'])
        except re.error as e:
            return jsonify({'success': False, 'message': f'正则表达式错误: {str(e)}'}), 400

    count, history_id, error = RenameRuleEngine.execute(
        album_id=album_id,
        photo_ids=clean_ids,
        rules=rules,
        excluded_ids=clean_excluded,
    )

    if error:
        return jsonify({'success': False, 'message': error}), 400

    return jsonify({
        'success': True,
        'message': f'成功重命名 {count} 张照片',
        'renamed_count': count,
        'history_id': history_id,
    })


@rename_bp.route('/api/history', methods=['GET'])
@login_required
def api_list_history():
    """列出重命名历史"""
    album_id = request.args.get('album_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    limit = min(max(limit, 1), 200)

    histories = RenameHistoryService.list_history(album_id=album_id, limit=limit)
    return jsonify({
        'success': True,
        'histories': [h.to_dict() for h in histories],
    })


@rename_bp.route('/api/history/<int:history_id>/rollback', methods=['POST'])
@login_required
def api_rollback(history_id):
    """回滚指定的重命名操作"""
    restored, error = RenameHistoryService.rollback(history_id)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    return jsonify({
        'success': True,
        'message': f'已成功回滚，恢复 {restored} 张照片的原始名称',
        'restored_count': restored,
    })


@rename_bp.route('/api/history/rollback-latest', methods=['POST'])
@login_required
def api_rollback_latest():
    """回滚最近一次批量重命名操作"""
    data = request.get_json() or {}
    album_id = data.get('album_id')
    history = RenameHistoryService.get_latest(album_id=album_id)
    if not history:
        return jsonify({'success': False, 'message': '没有可回滚的操作'}), 400
    restored, error = RenameHistoryService.rollback(history.id)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    return jsonify({
        'success': True,
        'message': f'已成功回滚最近一次操作，恢复 {restored} 张照片的原始名称',
        'restored_count': restored,
        'history_id': history.id,
    })
