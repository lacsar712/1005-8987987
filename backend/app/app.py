import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
from .db import db, Album, Photo, Highlight, CurationConfig, Template, PhotoPlaceholder
from .services import (
    TimelineService, OnThisDayService, PhotoDateGrouper,
    TemplateSeeder, TemplateService, TemplateApplier, PlaceholderService,
    WatermarkConfigService, AlbumWatermarkService, WatermarkProcessor,
    RenameRuleEngine, RenameHistoryService
)
from .routes import templates_bp, watermark_bp, rename_bp
from datetime import datetime, timedelta

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = '123456'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_curation_config():
    config = CurationConfig.query.first()
    if not config:
        config = CurationConfig(curation_text='', slideshow_interval=3)
        db.session.add(config)
        db.session.commit()
    return config

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/data/photos.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

    db.init_app(app)
    app.register_blueprint(templates_bp)
    app.register_blueprint(watermark_bp)
    app.register_blueprint(rename_bp)

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == '1':
            return User(id='1')
        return None

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    with app.app_context():
        db.create_all()
        TemplateSeeder.seed_builtin_templates()
        if Album.query.count() == 0:
            default_album = Album(title="我的首个相册", description="欢迎使用在线相册系统")
            db.session.add(default_album)
            db.session.commit()
        get_or_create_curation_config()
        WatermarkConfigService.get_config()

    @app.route('/')
    def index():
        albums = Album.query.order_by(Album.created_at.desc()).all()
        return render_template('index.html', albums=albums)

    @app.route('/album/<int:album_id>')
    def album_detail(album_id):
        album = Album.query.get_or_404(album_id)
        highlighted_ids = set()
        if current_user.is_authenticated:
            highlighted_ids = set(h.photo_id for h in Highlight.query.all())
        placeholders = PhotoPlaceholder.query.filter_by(album_id=album.id).order_by(PhotoPlaceholder.slot_index.asc()).all()
        layout_config = album.get_layout_config()
        tags = album.get_tags_list()
        return render_template('album.html', album=album, highlighted_ids=highlighted_ids,
                          placeholders=placeholders, layout_config=layout_config, tags=tags)

    @app.route('/highlights')
    def highlights():
        highlights = Highlight.query.order_by(Highlight.sort_order.asc(), Highlight.created_at.desc()).all()
        photos_with_highlights = []
        for h in highlights:
            photo = Photo.query.get(h.photo_id)
            if photo:
                photos_with_highlights.append({'photo': photo, 'highlight': h})
        config = get_or_create_curation_config()
        return render_template('highlights.html', 
                             highlights_data=photos_with_highlights, 
                             config=config,
                             current_user=current_user)

    @app.route('/admin/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                user = User(id='1')
                login_user(user)
                flash('登录成功', 'success')
                return redirect(url_for('index'))
            else:
                flash('用户名或密码错误', 'error')
        return render_template('login.html')

    @app.route('/admin/logout')
    @login_required
    def logout():
        logout_user()
        flash('已退出登录', 'info')
        return redirect(url_for('index'))

    @app.route('/album/create', methods=['GET', 'POST'])
    @login_required
    def create_album():
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            template_id = request.form.get('template_id', type=int)
            if not title:
                flash('相册名称不能为空', 'error')
            else:
                new_album = Album(title=title, description=description or '')
                db.session.add(new_album)
                db.session.flush()

                if template_id:
                    template = TemplateService.get_by_id(template_id)
                    if template:
                        TemplateApplier.apply_template_to_album(new_album, template)
                else:
                    db.session.commit()

                flash('相册创建成功', 'success')
                return redirect(url_for('index'))
        templates = TemplateService.get_all(active_only=True)
        return render_template('create_album.html', templates=templates)

    @app.route('/album/delete/<int:album_id>')
    @login_required
    def delete_album(album_id):
        album = Album.query.get_or_404(album_id)
        for photo in album.photos:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
            except OSError:
                pass
        db.session.delete(album)
        db.session.commit()
        flash('相册已删除', 'success')
        return redirect(url_for('index'))

    @app.route('/upload/<int:album_id>', methods=['GET', 'POST'])
    @login_required
    def upload_photo(album_id):
        album = Album.query.get_or_404(album_id)
        if request.method == 'POST':
            if 'photo' not in request.files:
                flash('没有文件被上传', 'error')
                return redirect(request.url)
            
            files = request.files.getlist('photo')
            uploaded_count = 0
            matched_placeholders = []

            placeholders = PhotoPlaceholder.query.filter_by(album_id=album.id).all()

            for file in files:
                if file.filename == '':
                    continue

                if file and allowed_file(file.filename):
                    original_filename = secure_filename(file.filename)
                    if not original_filename:
                        original_filename = "未命名图片"
                    
                    try:
                        extension = file.filename.rsplit('.', 1)[1].lower()
                    except IndexError:
                        continue

                    unique_filename = f"{uuid.uuid4().hex}.{extension}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(save_path)

                    width, height = None, None
                    exif_taken_at = None
                    exif_camera_model = None
                    try:
                        with Image.open(save_path) as img:
                            width, height = img.size
                            try:
                                exif_data = img._getexif()
                                if exif_data:
                                    exif_tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif_data.items()}
                                    date_str = exif_tag_map.get('DateTimeOriginal') or exif_tag_map.get('DateTime')
                                    if date_str:
                                        try:
                                            exif_taken_at = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                                        except (ValueError, TypeError):
                                            pass
                                    make = exif_tag_map.get('Make', '') or ''
                                    model = exif_tag_map.get('Model', '') or ''
                                    camera_parts = [p.strip() for p in [make, model] if p and p.strip()]
                                    if camera_parts:
                                        exif_camera_model = ' '.join(camera_parts)[:100] or None
                            except Exception:
                                pass
                    except Exception:
                        pass

                    resolved = AlbumWatermarkService.resolve_effective_config(album.id)
                    if resolved and resolved['enabled']:
                        try:
                            wm_processor = WatermarkProcessor(app.config['UPLOAD_FOLDER'])
                            wm_processor.process_image(
                                save_path,
                                resolved['config'],
                                effective_text=resolved['effective_text'],
                                effective_position=resolved['effective_position'],
                            )
                        except Exception:
                            pass

                    photo_aspect_ratio = None
                    if width and height and height > 0:
                        photo_aspect_ratio = round(width / height, 2)

                    new_photo = Photo(
                        filename=unique_filename,
                        original_filename=original_filename,
                        album_id=album.id,
                        exif_taken_at=exif_taken_at,
                        exif_camera_model=exif_camera_model,
                        width=width,
                        height=height,
                    )

                    matched = PlaceholderService.find_best_matching_placeholder(placeholders, photo_aspect_ratio)
                    if matched:
                        new_photo.replaced_placeholder_id = matched.id
                        matched.is_replaced = True
                        matched_placeholders.append({
                            'photo_filename': original_filename,
                            'slot_index': matched.slot_index,
                            'placeholder_ratio': matched.aspect_ratio,
                            'photo_ratio': photo_aspect_ratio,
                        })
                        placeholders = [p for p in placeholders if p.id != matched.id]

                    db.session.add(new_photo)
                    uploaded_count += 1
            
            if uploaded_count > 0:
                db.session.commit()
                msg = f'成功上传 {uploaded_count} 张图片'
                if matched_placeholders:
                    msg += f'，其中 {len(matched_placeholders)} 张已自动匹配占位槽位'
                flash(msg, 'success')
                return redirect(url_for('album_detail', album_id=album.id))
            else:
                flash('未选择有效文件或格式不支持', 'error')

        placeholders = PhotoPlaceholder.query.filter_by(album_id=album.id).order_by(PhotoPlaceholder.slot_index.asc()).all()
        return render_template('upload.html', album=album, placeholders=placeholders)

    @app.route('/photo/delete/<int:photo_id>')
    @login_required
    def delete_photo(photo_id):
        photo = Photo.query.get_or_404(photo_id)
        album_id = photo.album_id
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
        except OSError:
            pass
        db.session.delete(photo)
        db.session.commit()
        flash('图片已删除', 'success')
        return redirect(url_for('album_detail', album_id=album_id))

    @app.route('/api/highlight/<int:photo_id>', methods=['POST'])
    @login_required
    def api_add_highlight(photo_id):
        photo = Photo.query.get_or_404(photo_id)
        existing = Highlight.query.filter_by(photo_id=photo_id).first()
        if existing:
            return jsonify({'success': False, 'message': '照片已在精选集中'})
        max_order = db.session.query(db.func.max(Highlight.sort_order)).scalar() or 0
        highlight = Highlight(photo_id=photo_id, sort_order=max_order + 1)
        db.session.add(highlight)
        db.session.commit()
        return jsonify({'success': True, 'message': '已加入精选', 'highlight_id': highlight.id})

    @app.route('/api/highlight/<int:photo_id>', methods=['DELETE'])
    @login_required
    def api_remove_highlight(photo_id):
        highlight = Highlight.query.filter_by(photo_id=photo_id).first()
        if not highlight:
            return jsonify({'success': False, 'message': '照片不在精选集中'})
        db.session.delete(highlight)
        db.session.commit()
        return jsonify({'success': True, 'message': '已移出精选'})

    @app.route('/api/highlights/reorder', methods=['POST'])
    @login_required
    def api_reorder_highlights():
        data = request.get_json()
        if not data or 'order' not in data:
            return jsonify({'success': False, 'message': '缺少排序数据'})
        for idx, photo_id in enumerate(data['order']):
            highlight = Highlight.query.filter_by(photo_id=photo_id).first()
            if highlight:
                highlight.sort_order = idx
        db.session.commit()
        return jsonify({'success': True, 'message': '排序已更新'})

    @app.route('/api/highlights/data')
    def api_highlights_data():
        highlights = Highlight.query.order_by(Highlight.sort_order.asc(), Highlight.created_at.desc()).all()
        result = []
        for h in highlights:
            photo = Photo.query.get(h.photo_id)
            if photo:
                album = Album.query.get(photo.album_id)
                result.append({
                    'photo_id': photo.id,
                    'filename': photo.filename,
                    'original_filename': photo.original_filename,
                    'album_id': album.id if album else None,
                    'album_title': album.title if album else '',
                    'sort_order': h.sort_order,
                    'url': url_for('static', filename='uploads/' + photo.filename)
                })
        return jsonify({'highlights': result})

    @app.route('/api/highlights/candidates')
    @login_required
    def api_highlight_candidates():
        highlight_ids = set(h.photo_id for h in Highlight.query.all())
        candidates = []
        
        recent_cutoff = datetime.utcnow() - timedelta(days=30)
        recent_photos = Photo.query.filter(
            Photo.id.notin_(highlight_ids),
            Photo.uploaded_at >= recent_cutoff
        ).order_by(Photo.uploaded_at.desc()).limit(10).all()
        
        selected_ids = set()
        for photo in recent_photos:
            selected_ids.add(photo.id)
            album = Album.query.get(photo.album_id)
            candidates.append({
                'photo_id': photo.id,
                'filename': photo.filename,
                'original_filename': photo.original_filename,
                'album_title': album.title if album else '',
                'url': url_for('static', filename='uploads/' + photo.filename),
                'reason': '近期上传'
            })
        
        for album in Album.query.all():
            album_photos = Photo.query.filter(
                Photo.album_id == album.id,
                Photo.id.notin_(highlight_ids),
                Photo.id.notin_(selected_ids)
            ).all()
            if album_photos:
                mid_photos = sorted(album_photos, key=lambda p: p.uploaded_at)[len(album_photos)//3:2*len(album_photos)//3]
                for photo in mid_photos[:2]:
                    selected_ids.add(photo.id)
                    candidates.append({
                        'photo_id': photo.id,
                        'filename': photo.filename,
                        'original_filename': photo.original_filename,
                        'album_title': album.title,
                        'url': url_for('static', filename='uploads/' + photo.filename),
                        'reason': f'《{album.title}》精选位置'
                    })
                    if len(candidates) >= 20:
                        break
            if len(candidates) >= 20:
                break
        
        return jsonify({'candidates': candidates})

    @app.route('/api/curation/config', methods=['GET'])
    def api_get_curation_config():
        config = get_or_create_curation_config()
        return jsonify({
            'curation_text': config.curation_text,
            'slideshow_interval': config.slideshow_interval
        })

    @app.route('/api/curation/config', methods=['POST'])
    @login_required
    def api_update_curation_config():
        data = request.get_json()
        config = get_or_create_curation_config()
        if 'curation_text' in data:
            config.curation_text = data['curation_text']
        if 'slideshow_interval' in data:
            try:
                interval = int(data['slideshow_interval'])
                if 1 <= interval <= 30:
                    config.slideshow_interval = interval
            except (ValueError, TypeError):
                pass
        db.session.commit()
        return jsonify({'success': True, 'message': '配置已更新'})

    @app.route('/timeline')
    def timeline():
        data = TimelineService.get_timeline_data(use_exif=False)
        on_this_day = OnThisDayService.get_photos_on_this_day(use_exif=False)
        return render_template(
            'timeline.html',
            timeline_data=data,
            on_this_day=on_this_day,
            current_user=current_user
        )

    @app.route('/api/timeline/photos')
    def api_timeline_photos():
        use_exif = request.args.get('mode', 'upload') == 'exif'
        album_ids_str = request.args.get('albums', '')
        album_ids = [int(x) for x in album_ids_str.split(',') if x.strip().isdigit()] if album_ids_str else None
        data = TimelineService.get_timeline_data(album_ids=album_ids, use_exif=use_exif)
        return jsonify(data)

    @app.route('/api/timeline/albums')
    def api_timeline_albums():
        data = TimelineService.get_timeline_data(use_exif=False)
        return jsonify({'albums': data['albums']})

    @app.route('/api/timeline/on-this-day')
    def api_timeline_on_this_day():
        use_exif = request.args.get('mode', 'upload') == 'exif'
        data = OnThisDayService.get_photos_on_this_day(use_exif=use_exif)
        return jsonify({'items': data})

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=8000)
