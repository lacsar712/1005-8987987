import os
from flask import Blueprint, request, jsonify, render_template, url_for, abort, send_from_directory, current_app
from flask_login import login_required
from ..db import db, Photo, Album
from ..services import PhotoEditService

photo_edit_bp = Blueprint('photo_edit', __name__)


@photo_edit_bp.route('/photo/<int:photo_id>/edit')
@login_required
def photo_edit_page(photo_id):
    """照片编辑器页面"""
    photo = Photo.query.get_or_404(photo_id)
    album = Album.query.get(photo.album_id)
    if not album:
        abort(404)

    PhotoEditService.ensure_original_backup(photo)
    edit_info = PhotoEditService.get_photo_edit_info(photo)

    base, ext = os.path.splitext(photo.filename)
    original_filename = f'{base}_original{ext}'
    original_url = url_for('photo_edit.serve_original', filename=photo.filename)

    return render_template(
        'photo_edit.html',
        photo=photo,
        album=album,
        original_url=original_url,
        edit_info=edit_info,
    )


@photo_edit_bp.route('/photo/original/<path:filename>')
@login_required
def serve_original(filename):
    """返回原图备份文件（供对比参考与编辑器使用）"""
    base, ext = os.path.splitext(filename)
    original_name = f'{base}_original{ext}'
    upload_folder = current_app.config['UPLOAD_FOLDER']
    original_path = os.path.join(upload_folder, original_name)

    if not os.path.exists(original_path):
        return send_from_directory(upload_folder, filename)
    return send_from_directory(upload_folder, original_name)


@photo_edit_bp.route('/api/photo/<int:photo_id>/edit-info', methods=['GET'])
@login_required
def api_get_edit_info(photo_id):
    """获取照片编辑信息"""
    photo = Photo.query.get_or_404(photo_id)
    info = PhotoEditService.get_photo_edit_info(photo)
    info['original_url'] = url_for('photo_edit.serve_original', filename=photo.filename)
    info['photo_url'] = url_for('static', filename='uploads/' + photo.filename)
    return jsonify({'success': True, 'data': info})


@photo_edit_bp.route('/api/photo/<int:photo_id>/version', methods=['POST'])
@login_required
def api_save_version(photo_id):
    """保存编辑版本（非破坏性保存操作序列）"""
    data = request.get_json() or {}
    operations = data.get('operations', [])
    label = data.get('label', '')
    thumbnail = data.get('thumbnail', '')

    if not isinstance(operations, list):
        return jsonify({'success': False, 'message': '操作序列格式错误'}), 400

    version, error = PhotoEditService.save_version(photo_id, operations, label, thumbnail)
    if error:
        return jsonify({'success': False, 'message': error}), 400

    return jsonify({
        'success': True,
        'message': '版本已保存',
        'version': version.to_dict(),
    })


@photo_edit_bp.route('/api/photo/<int:photo_id>/versions', methods=['GET'])
@login_required
def api_list_versions(photo_id):
    """列出照片的所有编辑版本"""
    versions = PhotoEditService.list_versions(photo_id)
    return jsonify({
        'success': True,
        'versions': [v.to_dict() for v in versions],
    })


@photo_edit_bp.route('/api/photo/<int:photo_id>/version/<int:version_id>/rollback', methods=['POST'])
@login_required
def api_rollback_version(photo_id, version_id):
    """回滚到指定版本"""
    ok, error = PhotoEditService.rollback_to_version(photo_id, version_id)
    if not ok:
        return jsonify({'success': False, 'message': error}), 400

    version = PhotoEditService.get_version(version_id)
    return jsonify({
        'success': True,
        'message': '已回滚到该版本',
        'operations': version.get_operations() if version else [],
    })


@photo_edit_bp.route('/api/photo/<int:photo_id>/commit', methods=['POST'])
@login_required
def api_commit_edit(photo_id):
    """合成编辑结果并覆盖主文件"""
    data = request.get_json() or {}
    operations = data.get('operations', [])

    if not isinstance(operations, list):
        return jsonify({'success': False, 'message': '操作序列格式错误'}), 400

    ok, error = PhotoEditService.commit_edit(photo_id, operations)
    if not ok:
        return jsonify({'success': False, 'message': error}), 400

    return jsonify({
        'success': True,
        'message': '编辑结果已保存',
    })
