import os
from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_from_directory, abort
from flask_login import login_required
from ..db import db, Album, UrlImportTask, UrlImportItem, Photo
from ..services.url_import_service import UrlImportProcessor


url_import_bp = Blueprint('url_import', __name__, url_prefix='/url-import')


def _get_previews_dir():
    uploads = current_app.config['UPLOAD_FOLDER']
    return os.path.join(os.path.dirname(uploads), 'url_import_previews')


def _get_processor():
    uploads = current_app.config['UPLOAD_FOLDER']
    return UrlImportProcessor(uploads)


@url_import_bp.route('')
@login_required
def import_page():
    """导入页面"""
    albums = Album.query.order_by(Album.created_at.desc()).all()
    processor = _get_processor()
    tasks = processor.list_recent_tasks(limit=5)
    return render_template('url_import.html', albums=albums, tasks=tasks)


@url_import_bp.route('/progress/<int:task_id>')
@login_required
def progress_page(task_id):
    """导入进度页面"""
    task = UrlImportTask.query.get_or_404(task_id)
    return render_template('url_import_progress.html', task=task)


@url_import_bp.route('/history')
@login_required
def history_page():
    """导入历史记录页面"""
    processor = _get_processor()
    tasks = processor.list_recent_tasks(limit=20)
    return render_template('url_import_history.html', tasks=tasks)


@url_import_bp.route('/api/start', methods=['POST'])
@login_required
def api_start_import():
    """启动导入任务"""
    data = request.get_json() or {}
    album_id = data.get('album_id')
    source_type = data.get('source_type', 'urls')
    source_data = data.get('source_data', '')

    if not album_id:
        return jsonify({'success': False, 'message': '请选择目标相册'}), 400
    if not source_data:
        return jsonify({'success': False, 'message': '请输入 URL 或网页地址'}), 400
    if source_type not in ('urls', 'page'):
        return jsonify({'success': False, 'message': '无效的来源类型'}), 400

    try:
        album_id = int(album_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '无效的相册 ID'}), 400

    processor = _get_processor()
    task, err = processor.start_task(album_id, source_type, source_data)
    if err:
        return jsonify({'success': False, 'message': err}), 400

    return jsonify({
        'success': True,
        'task': task.to_dict(),
        'progress_url': url_for('url_import.progress_page', task_id=task.id),
    })


@url_import_bp.route('/api/task/<int:task_id>', methods=['GET'])
@login_required
def api_get_task(task_id):
    """获取任务状态"""
    task = UrlImportTask.query.get_or_404(task_id)
    processor = _get_processor()
    is_running = processor.is_task_running(task_id)
    return jsonify({
        'task': task.to_dict(),
        'is_running': is_running,
    })


@url_import_bp.route('/api/task/<int:task_id>/items', methods=['GET'])
@login_required
def api_get_task_items(task_id):
    """获取任务条目列表"""
    task = UrlImportTask.query.get_or_404(task_id)
    status_filter = request.args.get('status')
    processor = _get_processor()
    items = processor.get_task_items(task_id, status_filter)

    result = []
    for item in items:
        d = item.to_dict()
        if item.duplicate_photo_id:
            dup = Photo.query.get(item.duplicate_photo_id)
            if dup:
                dup_album = Album.query.get(dup.album_id)
                d['duplicate_photo'] = {
                    'id': dup.id,
                    'album_id': dup.album_id,
                    'album_title': dup_album.title if dup_album else '',
                    'filename': dup.filename,
                    'original_filename': dup.original_filename,
                    'url': url_for('static', filename='uploads/' + dup.filename),
                }
        if item.photo_id and item.saved_filename:
            d['photo_url'] = url_for('static', filename='uploads/' + item.saved_filename)
        if item.preview_filename:
            d['preview_url'] = url_for('url_import.preview_image', filename=item.preview_filename)
        result.append(d)

    return jsonify({'items': result})


@url_import_bp.route('/api/item/<int:item_id>/decision', methods=['POST'])
@login_required
def api_resolve_decision(item_id):
    """处理疑似重复项的决策"""
    data = request.get_json() or {}
    decision = data.get('decision')
    album_id = data.get('album_id')

    if decision not in ('import', 'skip'):
        return jsonify({'success': False, 'message': '无效的决策'}), 400

    processor = _get_processor()
    ok, err = processor.resolve_decision(item_id, decision, album_id)
    if err:
        return jsonify({'success': False, 'message': err}), 400

    item = UrlImportItem.query.get(item_id)
    return jsonify({
        'success': True,
        'item': item.to_dict() if item else None,
    })


@url_import_bp.route('/api/albums', methods=['GET'])
@login_required
def api_list_albums():
    """列出所有相册（供前端下拉选择）"""
    albums = Album.query.order_by(Album.created_at.desc()).all()
    result = []
    for a in albums:
        result.append({
            'id': a.id,
            'title': a.title,
            'photo_count': len(a.photos),
        })
    return jsonify({'albums': result})


@url_import_bp.route('/preview/<path:filename>')
@login_required
def preview_image(filename):
    """预览疑似重复项的待导入图片"""
    if '..' in filename or filename.startswith('/'):
        abort(404)
    previews_dir = _get_previews_dir()
    if not os.path.exists(os.path.join(previews_dir, filename)):
        abort(404)
    return send_from_directory(previews_dir, filename)
