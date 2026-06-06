from .app import create_app
from .db import db, Album, Photo
import datetime
import random
import os


def seed():
    app = create_app()
    with app.app_context():
        if Album.query.count() == 0:
            print("🌱 正在进行初始数据填充...")

            today = datetime.datetime.now()

            public_album = Album(
                title="我的精选相册",
                description="这是系统自动生成的初始相册，用于展示功能。",
                is_admin_only=False
            )
            db.session.add(public_album)

            travel_album = Album(
                title="旅行记忆",
                description="记录旅途中的美好瞬间",
                is_admin_only=False
            )
            db.session.add(travel_album)

            daily_album = Album(
                title="日常点滴",
                description="平凡日子里的小确幸",
                is_admin_only=False
            )
            db.session.add(daily_album)

            admin_album = Album(
                title="私密相册（仅管理员可见）",
                description="此相册的照片不会出现在时间线和精选集中",
                is_admin_only=True
            )
            db.session.add(admin_album)
            db.session.commit()

            uploads_dir = app.config['UPLOAD_FOLDER']
            os.makedirs(uploads_dir, exist_ok=True)

            sample_extensions = ['jpg', 'png', 'jpeg']
            albums_for_photos = [public_album, travel_album, daily_album]

            photo_count = 0
            for album_idx, album in enumerate(albums_for_photos):
                for i in range(15):
                    days_ago = album_idx * 50 + i * random.randint(1, 10)
                    uploaded_at = today - datetime.timedelta(days=days_ago, hours=random.randint(0, 23))
                    has_exif = random.random() > 0.3
                    exif_taken_at = None
                    if has_exif:
                        exif_taken_at = uploaded_at - datetime.timedelta(days=random.randint(0, 2))

                    ext = random.choice(sample_extensions)
                    filename = f"seed_{album.id}_{i}.{ext}"
                    original_filename = f"照片_{album.id}_{i + 1}.{ext}"

                    filepath = os.path.join(uploads_dir, filename)
                    if not os.path.exists(filepath):
                        with open(filepath, 'wb') as f:
                            f.write(b'\x89PNG\r\n\x1a\n')

                    photo = Photo(
                        filename=filename,
                        original_filename=original_filename,
                        album_id=album.id,
                        uploaded_at=uploaded_at,
                        exif_taken_at=exif_taken_at
                    )
                    db.session.add(photo)
                    photo_count += 1

            db.session.commit()
            print(f"✅ 数据填充完成：{len(albums_for_photos) + 1} 个相册，{photo_count} 张照片。")
        else:
            print("✨ 数据库已存在数据，跳过填充。")


if __name__ == '__main__':
    seed()
