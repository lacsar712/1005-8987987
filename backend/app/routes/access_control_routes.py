from flask import (
    Blueprint, request, jsonify, render_template, redirect, url_for,
    session, flash, send_file, current_app
)
from flask_login import login_required, current_user
from ..db import db, Album
from ..services import (
    GuestAccessConfigService, GuestInviteService, AlbumAccessTokenService
)

access_control_bp = Blueprint('access_control', __name__)


def _get_base_url():
    return request.url_root.rstrip('/')


@access_control_bp.route('/guest-gate', methods=['GET', 'POST'])
def guest_gate():
    """访客门禁页"""
    config = GuestAccessConfigService.get_config()

    if not config.enabled or not config.password:
        return redirect(url_for('index'))

    prefill_code = request.args.get('prefill', '')
    error_msg = None
    next_url = request.args.get('next', url_for('index'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        invite_code = request.form.get('invite_code', '').strip()

        if invite_code:
            invite = GuestInviteService.validate_and_use(invite_code)
            if invite:
                session['guest_authenticated'] = True
                session['guest_config_version'] = config.config_version
                session['guest_album_scope'] = invite.get_album_scope_ids()
                session['guest_invite_code'] = invite_code
                flash('验证成功，欢迎访问', 'success')
                return redirect(next_url or url_for('index'))
            else:
                error_msg = '邀请码无效或已过期'

        if GuestAccessConfigService.verify_password(password):
            session['guest_authenticated'] = True
            session['guest_config_version'] = config.config_version
            session['guest_album_scope'] = []
            session.pop('guest_invite_code', None)
            flash('验证成功，欢迎访问', 'success')
            return redirect(next_url or url_for('index'))
        elif password:
            error_msg = '口令错误'
        elif not invite_code:
            error_msg = '请输入口令或邀请码'

    return render_template(
        'guest_gate.html',
        config=config,
        prefill_code=prefill_code,
        error_msg=error_msg,
        next_url=next_url
    )


@access_control_bp.route('/guest-logout')
def guest_logout():
    """访客退出"""
    session.pop('guest_authenticated', None)
    session.pop('guest_config_version', None)
    session.pop('guest_album_scope', None)
    session.pop('guest_invite_code', None)
    session.pop('album_access_token', None)
    flash('已退出访客模式', 'info')
    return redirect(url_for('index'))


@access_control_bp.route('/invite/<code>')
def invite_entry(code):
    """邀请码入口，扫码后跳转"""
    invite = GuestInviteService.get_by_code(code)
    if not invite or not invite.is_valid():
        flash('邀请码无效或已过期', 'error')
        return redirect(url_for('index'))

    config = GuestAccessConfigService.get_config()
    if not config.enabled:
        session['guest_authenticated'] = True
        session['guest_config_version'] = config.config_version
        session['guest_album_scope'] = invite.get_album_scope_ids()
        session['guest_invite_code'] = code
        return redirect(url_for('index'))

    return redirect(url_for('access_control.guest_gate', prefill=code))


@access_control_bp.route('/admin/access-control')
@login_required
def access_control_settings_page():
    """访问控制设置页面"""
    config = GuestAccessConfigService.get_config()
    albums = Album.query.order_by(Album.created_at.desc()).all()
    invites = GuestInviteService.list_all()
    tokens = AlbumAccessTokenService.list_all()
    return render_template(
        'access_control_settings.html',
        config=config,
        albums=albums,
        invites=invites,
        tokens=tokens
    )


@access_control_bp.route('/api/access-control/config', methods=['GET'])
def api_get_config():
    """获取访问控制配置"""
    config = GuestAccessConfigService.get_config()
    data = config.to_dict()
    data.pop('password', None)
    data['has_password'] = bool(config.password)
    return jsonify({'config': data})


@access_control_bp.route('/api/access-control/config', methods=['POST'])
@login_required
def api_update_config():
    """更新访问控制配置"""
    data = request.get_json() or {}
    try:
        config = GuestAccessConfigService.update_config(data)
        result = config.to_dict()
        result.pop('password', None)
        result['has_password'] = bool(config.password)
        return jsonify({'success': True, 'config': result})
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@access_control_bp.route('/api/access-control/invites', methods=['GET'])
@login_required
def api_list_invites():
    """列出所有邀请码"""
    invites = GuestInviteService.list_all()
    return jsonify({'invites': [i.to_dict() for i in invites]})


@access_control_bp.route('/api/access-control/invites', methods=['POST'])
@login_required
def api_create_invite():
    """创建新邀请码"""
    data = request.get_json() or {}
    expires_hours = int(data.get('expires_hours', 24))
    max_uses = int(data.get('max_uses', 0))
    album_scope_ids = data.get('album_scope_ids', []) or []
    if expires_hours < 1:
        expires_hours = 1
    invite = GuestInviteService.generate_code(
        expires_hours=expires_hours,
        max_uses=max_uses,
        album_scope_ids=album_scope_ids
    )
    return jsonify({'success': True, 'invite': invite.to_dict()})


@access_control_bp.route('/api/access-control/invites/<int:invite_id>/revoke', methods=['POST'])
@login_required
def api_revoke_invite(invite_id):
    """撤销邀请码"""
    invite = GuestInviteService.revoke(invite_id)
    if not invite:
        return jsonify({'success': False, 'message': '邀请码不存在'}), 404
    return jsonify({'success': True, 'invite': invite.to_dict()})


@access_control_bp.route('/api/access-control/invites/<code>/qrcode')
@login_required
def api_invite_qrcode(code):
    """生成邀请码 QR 图片"""
    invite = GuestInviteService.get_by_code(code)
    if not invite:
        return jsonify({'success': False, 'message': '邀请码不存在'}), 404
    buf = GuestInviteService.generate_qr_svg(code, _get_base_url())
    if not buf:
        return jsonify({'success': False, 'message': 'QR 码生成库未安装'}), 500
    return send_file(buf, mimetype='image/png', cache_timeout=0)


@access_control_bp.route('/api/access-control/tokens', methods=['GET'])
@login_required
def api_list_tokens():
    """列出所有相册访问令牌"""
    tokens = AlbumAccessTokenService.list_all()
    return jsonify({'tokens': [t.to_dict() for t in tokens]})


@access_control_bp.route('/api/access-control/tokens', methods=['POST'])
@login_required
def api_create_token():
    """创建新相册访问令牌"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    album_ids = data.get('album_ids', []) or []
    expires_hours = data.get('expires_hours')
    if expires_hours is not None:
        try:
            expires_hours = int(expires_hours)
            if expires_hours < 1:
                expires_hours = None
        except (ValueError, TypeError):
            expires_hours = None

    if not album_ids:
        return jsonify({'success': False, 'message': '至少选择一个相册'}), 400

    token = AlbumAccessTokenService.create_token(
        name=name,
        album_ids=album_ids,
        expires_hours=expires_hours
    )
    return jsonify({'success': True, 'token': token.to_dict()})


@access_control_bp.route('/api/access-control/tokens/<int:token_id>', methods=['PUT'])
@login_required
def api_update_token(token_id):
    """更新相册访问令牌"""
    data = request.get_json() or {}
    token = AlbumAccessTokenService.update_token(
        token_id=token_id,
        name=data.get('name'),
        album_ids=data.get('album_ids'),
        is_active=data.get('is_active')
    )
    if not token:
        return jsonify({'success': False, 'message': '令牌不存在'}), 404
    return jsonify({'success': True, 'token': token.to_dict()})


@access_control_bp.route('/api/access-control/tokens/<int:token_id>/revoke', methods=['POST'])
@login_required
def api_revoke_token(token_id):
    """撤销相册访问令牌"""
    token = AlbumAccessTokenService.revoke(token_id)
    if not token:
        return jsonify({'success': False, 'message': '令牌不存在'}), 404
    return jsonify({'success': True, 'token': token.to_dict()})


@access_control_bp.route('/album-access/<token>')
def album_access_entry(token):
    """相册访问令牌入口（分域访问）"""
    access_token = AlbumAccessTokenService.validate_token(token)
    if not access_token:
        flash('访问令牌无效或已过期', 'error')
        return redirect(url_for('index'))

    session['album_access_token'] = token
    session['guest_authenticated'] = True
    config = GuestAccessConfigService.get_config()
    session['guest_config_version'] = config.config_version
    session['guest_album_scope'] = access_token.get_album_ids()
    flash(f'已通过令牌访问：{access_token.name}', 'success')
    return redirect(url_for('index'))
