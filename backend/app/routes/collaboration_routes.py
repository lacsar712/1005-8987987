import os
from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for,
    session, flash, current_app, abort
)
from flask_login import login_required, current_user
from ..db import db, Album, CollaborationLink, CollaborationPhoto
from ..services import CollaborationLinkService, CollaborationPhotoService


collaboration_bp = Blueprint('collaboration', __name__)


def _get_base_url():
    return request.url_root.rstrip('/')


@collaboration_bp.route('/collaborate/<token>', methods=['GET', 'POST'])
def collaborate_upload_page(token):
    """访客协作上传页面（无需登录）"""
    link = CollaborationLinkService.get_by_token(token)
    if not link:
        abort(404)
    if not link.is_valid():
        return render_template('collaboration_invalid.html', link=link)

    if request.method == 'POST':
        files = request.files.getlist('photo')
        contributor_name = request.form.get('contributor_name', '').strip()
        message = request.form.get('message', '').strip()
        uploaded_count = 0
        errors = []

        for file in files:
            if not file or not file.filename:
                continue
            photo, err = CollaborationPhotoService.upload_photo(
                link, file, contributor_name=contributor_name, message=message
            )
            if photo:
                uploaded_count += 1
            else:
                errors.append(err)

        if uploaded_count > 0:
            msg = f'成功上传 {uploaded_count} 张照片，等待管理员审核'
            flash(msg, 'success')
            return redirect(url_for('collaboration.collaborate_upload_page', token=token))
        else:
            flash(errors[0] if errors else '未选择有效文件', 'error')

    stats = link.get_stats()
    remaining = None
    if link.max_uploads > 0:
        remaining = max(0, link.max_uploads - (stats['total'] - stats['rejected']))

    return render_template(
        'collaboration_upload.html',
        link=link,
        album=link.album,
        stats=stats,
        remaining=remaining,
        base_url=_get_base_url(),
    )


@collaboration_bp.route('/admin/collaboration')
@login_required
def collaboration_management_page():
    """协作管理页面"""
    links = CollaborationLinkService.list_all()
    album_models = Album.query.order_by(Album.created_at.desc()).all()
    albums = [{'id': a.id, 'title': a.title, 'photo_count': len(a.photos)} for a in album_models]
    pending_stats = CollaborationPhotoService.get_pending_stats()
    return render_template(
        'collaboration_management.html',
        links=links,
        albums=albums,
        pending_stats=pending_stats,
        base_url=_get_base_url(),
    )


@collaboration_bp.route('/admin/collaboration/review')
@login_required
def collaboration_review_page():
    """协作审核页面"""
    album_id = request.args.get('album_id', type=int)
    link_id = request.args.get('link_id', type=int)
    pending_photos = CollaborationPhotoService.list_pending(album_id=album_id, link_id=link_id)
    album_models = Album.query.order_by(Album.created_at.desc()).all()
    albums = [{'id': a.id, 'title': a.title} for a in album_models]
    link_models = CollaborationLinkService.list_all()
    links = [{'id': l.id, 'name': l.name or l.token[:12]} for l in link_models]
    pending_stats = CollaborationPhotoService.get_pending_stats()
    return render_template(
        'collaboration_review.html',
        pending_photos=pending_photos,
        albums=albums,
        links=links,
        current_album_id=album_id,
        current_link_id=link_id,
        pending_stats=pending_stats,
    )


@collaboration_bp.route('/api/collaboration/links', methods=['GET'])
@login_required
def api_list_links():
    """列出所有协作链接"""
    album_id = request.args.get('album_id', type=int)
    if album_id:
        links = CollaborationLinkService.list_by_album(album_id)
    else:
        links = CollaborationLinkService.list_all()
    return jsonify({'links': [l.to_dict() for l in links]})


@collaboration_bp.route('/api/collaboration/links', methods=['POST'])
@login_required
def api_create_link():
    """创建协作链接"""
    data = request.get_json() or {}
    album_id = data.get('album_id')
    name = data.get('name', '').strip()
    expires_hours = data.get('expires_hours')
    max_uploads = data.get('max_uploads', 0)

    if not album_id:
        return jsonify({'success': False, 'message': '请选择目标相册'}), 400

    try:
        album_id = int(album_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': '无效的相册 ID'}), 400

    if expires_hours is not None:
        try:
            expires_hours = int(expires_hours)
            if expires_hours < 1:
                expires_hours = None
        except (ValueError, TypeError):
            expires_hours = None

    try:
        max_uploads = int(max_uploads) if max_uploads else 0
    except (ValueError, TypeError):
        max_uploads = 0

    link, err = CollaborationLinkService.create_link(
        album_id=album_id,
        name=name,
        expires_hours=expires_hours,
        max_uploads=max_uploads,
    )
    if err:
        return jsonify({'success': False, 'message': err}), 400

    return jsonify({
        'success': True,
        'link': link.to_dict(),
        'share_url': f"{_get_base_url()}/collaborate/{link.token}",
    })


@collaboration_bp.route('/api/collaboration/links/<int:link_id>', methods=['PUT'])
@login_required
def api_update_link(link_id):
    """更新协作链接"""
    data = request.get_json() or {}
    link = CollaborationLinkService.update(
        link_id=link_id,
        name=data.get('name'),
        expires_hours=data.get('expires_hours'),
        max_uploads=data.get('max_uploads'),
    )
    if not link:
        return jsonify({'success': False, 'message': '链接不存在'}), 404
    return jsonify({'success': True, 'link': link.to_dict()})


@collaboration_bp.route('/api/collaboration/links/<int:link_id>/revoke', methods=['POST'])
@login_required
def api_revoke_link(link_id):
    """撤销协作链接"""
    link = CollaborationLinkService.revoke(link_id)
    if not link:
        return jsonify({'success': False, 'message': '链接不存在'}), 404
    return jsonify({'success': True, 'link': link.to_dict()})


@collaboration_bp.route('/api/collaboration/links/<int:link_id>/reactivate', methods=['POST'])
@login_required
def api_reactivate_link(link_id):
    """重新启用协作链接"""
    link = CollaborationLinkService.reactivate(link_id)
    if not link:
        return jsonify({'success': False, 'message': '链接不存在'}), 404
    return jsonify({'success': True, 'link': link.to_dict()})


@collaboration_bp.route('/api/collaboration/links/<int:link_id>', methods=['DELETE'])
@login_required
def api_delete_link(link_id):
    """删除协作链接"""
    ok = CollaborationLinkService.delete(link_id)
    if not ok:
        return jsonify({'success': False, 'message': '链接不存在'}), 404
    return jsonify({'success': True})


@collaboration_bp.route('/api/collaboration/photos/pending', methods=['GET'])
@login_required
def api_list_pending_photos():
    """列出待审核的协作照片"""
    album_id = request.args.get('album_id', type=int)
    link_id = request.args.get('link_id', type=int)
    photos = CollaborationPhotoService.list_pending(album_id=album_id, link_id=link_id)
    return jsonify({'photos': [p.to_dict() for p in photos]})


@collaboration_bp.route('/api/collaboration/photos/<int:photo_id>/approve', methods=['POST'])
@login_required
def api_approve_photo(photo_id):
    """批准单张协作照片"""
    photo, err = CollaborationPhotoService.approve(photo_id)
    if err:
        return jsonify({'success': False, 'message': err}), 400
    return jsonify({'success': True, 'photo': photo.to_dict()})


@collaboration_bp.route('/api/collaboration/photos/<int:photo_id>/reject', methods=['POST'])
@login_required
def api_reject_photo(photo_id):
    """拒绝单张协作照片"""
    photo, err = CollaborationPhotoService.reject(photo_id)
    if err:
        return jsonify({'success': False, 'message': err}), 400
    return jsonify({'success': True, 'photo': photo.to_dict()})


@collaboration_bp.route('/api/collaboration/photos/batch-approve', methods=['POST'])
@login_required
def api_batch_approve():
    """批量批准协作照片"""
    data = request.get_json() or {}
    photo_ids = data.get('photo_ids', []) or []
    if not photo_ids:
        return jsonify({'success': False, 'message': '未选择照片'}), 400
    results, errors = CollaborationPhotoService.batch_approve(photo_ids)
    return jsonify({
        'success': True,
        'approved_count': len(results),
        'errors': errors,
        'photos': [p.to_dict() for p in results],
    })


@collaboration_bp.route('/api/collaboration/photos/batch-reject', methods=['POST'])
@login_required
def api_batch_reject():
    """批量拒绝协作照片"""
    data = request.get_json() or {}
    photo_ids = data.get('photo_ids', []) or []
    if not photo_ids:
        return jsonify({'success': False, 'message': '未选择照片'}), 400
    results, errors = CollaborationPhotoService.batch_reject(photo_ids)
    return jsonify({
        'success': True,
        'rejected_count': len(results),
        'errors': errors,
    })


@collaboration_bp.route('/api/collaboration/stats/pending', methods=['GET'])
@login_required
def api_pending_stats():
    """获取待审核统计"""
    stats = CollaborationPhotoService.get_pending_stats()
    return jsonify({'stats': stats})


@collaboration_bp.route('/api/collaboration/albums', methods=['GET'])
@login_required
def api_list_albums():
    """列出所有相册（供前端下拉选择）"""
    albums = Album.query.order_by(Album.created_at.desc()).all()
    result = []
    for a in albums:
        pending = CollaborationPhoto.query.filter_by(album_id=a.id, status='pending').count()
        result.append({
            'id': a.id,
            'title': a.title,
            'photo_count': len(a.photos),
            'pending_count': pending,
        })
    return jsonify({'albums': result})
