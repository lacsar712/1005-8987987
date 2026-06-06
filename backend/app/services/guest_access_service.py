import uuid
import secrets
import io
from datetime import datetime, timedelta
from ..db import db, GuestAccessConfig, GuestInviteCode, AlbumAccessToken

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


class GuestAccessConfigService:
    """访客访问配置服务"""

    @staticmethod
    def get_config():
        config = GuestAccessConfig.query.first()
        if not config:
            config = GuestAccessConfig(
                enabled=False,
                password='',
                welcome_text='欢迎访问，请输入访客口令',
                config_version=1
            )
            db.session.add(config)
            db.session.commit()
        return config

    @staticmethod
    def update_config(data):
        config = GuestAccessConfigService.get_config()
        version_changed = False

        if 'enabled' in data:
            new_enabled = bool(data['enabled'])
            if config.enabled != new_enabled:
                config.enabled = new_enabled
                version_changed = True

        if 'password' in data:
            new_pwd = str(data['password']).strip()
            if new_pwd and (len(new_pwd) < 4 or len(new_pwd) > 8 or not new_pwd.isdigit()):
                raise ValueError('口令必须为4-8位数字')
            if config.password != new_pwd:
                config.password = new_pwd
                if new_pwd:
                    version_changed = True

        if 'welcome_text' in data:
            config.welcome_text = str(data['welcome_text']).strip()[:500]

        if version_changed:
            config.config_version += 1

        db.session.commit()
        return config

    @staticmethod
    def is_enabled():
        config = GuestAccessConfigService.get_config()
        return config.enabled and bool(config.password)

    @staticmethod
    def verify_password(password):
        config = GuestAccessConfigService.get_config()
        if not config.enabled or not config.password:
            return True
        return password and password.strip() == config.password

    @staticmethod
    def get_config_version():
        config = GuestAccessConfigService.get_config()
        return config.config_version


class GuestInviteService:
    """访客邀请码服务"""

    @staticmethod
    def generate_code(expires_hours=24, max_uses=0, album_scope_ids=None):
        code = secrets.token_urlsafe(16)
        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
        invite = GuestInviteCode(
            code=code,
            expires_at=expires_at,
            max_uses=max_uses,
            used_count=0,
            is_active=True
        )
        invite.set_album_scope_ids(album_scope_ids or [])
        db.session.add(invite)
        db.session.commit()
        return invite

    @staticmethod
    def get_by_code(code):
        return GuestInviteCode.query.filter_by(code=code).first()

    @staticmethod
    def validate_and_use(code):
        invite = GuestInviteService.get_by_code(code)
        if not invite or not invite.is_valid():
            return None
        invite.used_count += 1
        db.session.commit()
        return invite

    @staticmethod
    def list_all():
        return GuestInviteCode.query.order_by(GuestInviteCode.created_at.desc()).all()

    @staticmethod
    def revoke(invite_id):
        invite = GuestInviteCode.query.get(invite_id)
        if invite:
            invite.is_active = False
            db.session.commit()
        return invite

    @staticmethod
    def generate_qr_svg(code, base_url):
        if not HAS_QRCODE:
            return None
        invite_url = f"{base_url.rstrip('/')}/invite/{code}"
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(invite_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf


class AlbumAccessTokenService:
    """相册组访问令牌服务（分域访问）"""

    @staticmethod
    def create_token(name, album_ids, expires_hours=None):
        token = secrets.token_urlsafe(24)
        expires_at = None
        if expires_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
        access_token = AlbumAccessToken(
            token=token,
            name=name or '未命名令牌',
            expires_at=expires_at,
            is_active=True
        )
        access_token.set_album_ids(album_ids or [])
        db.session.add(access_token)
        db.session.commit()
        return access_token

    @staticmethod
    def get_by_token(token):
        if not token:
            return None
        return AlbumAccessToken.query.filter_by(token=token).first()

    @staticmethod
    def validate_token(token):
        access_token = AlbumAccessTokenService.get_by_token(token)
        if not access_token or not access_token.is_valid():
            return None
        return access_token

    @staticmethod
    def list_all():
        return AlbumAccessToken.query.order_by(AlbumAccessToken.created_at.desc()).all()

    @staticmethod
    def revoke(token_id):
        access_token = AlbumAccessToken.query.get(token_id)
        if access_token:
            access_token.is_active = False
            db.session.commit()
        return access_token

    @staticmethod
    def update_token(token_id, name=None, album_ids=None, is_active=None):
        access_token = AlbumAccessToken.query.get(token_id)
        if not access_token:
            return None
        if name is not None:
            access_token.name = name
        if album_ids is not None:
            access_token.set_album_ids(album_ids)
        if is_active is not None:
            access_token.is_active = is_active
        db.session.commit()
        return access_token
