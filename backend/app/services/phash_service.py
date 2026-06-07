import os
from PIL import Image


PHASH_DISTANCE_THRESHOLD = 8


def _compute_dhash(image, hash_size=8):
    """
    计算 Difference Hash (dHash) - 基于相邻像素差异
    比 pHash 更快，资源消耗更低
    """
    resized = image.convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
    pixels = list(resized.getdata())
    difference = []
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            difference.append(left > right)
    hex_str = ''
    for i in range(0, len(difference), 4):
        nibble = difference[i:i + 4]
        value = 0
        for j, bit in enumerate(nibble):
            if bit:
                value |= (1 << (3 - j))
        hex_str += format(value, 'x')
    return hex_str


def _compute_phash_fallback(image, hash_size=8):
    """
    备用 pHash 实现：基于 Pillow 的 DCT 简化版
    """
    return _compute_dhash(image, hash_size)


def compute_phash(image_path=None, image_obj=None):
    """
    计算图片的感知哈希值
    优先使用 imagehash 库，不可用时使用 fallback 实现
    """
    try:
        import imagehash
        if image_obj is not None:
            return str(imagehash.phash(image_obj))
        if image_path and os.path.exists(image_path):
            with Image.open(image_path) as img:
                return str(imagehash.phash(img))
    except ImportError:
        pass

    if image_obj is not None:
        return _compute_phash_fallback(image_obj)
    if image_path and os.path.exists(image_path):
        with Image.open(image_path) as img:
            return _compute_phash_fallback(img)
    return None


def hamming_distance(hash1, hash2):
    """
    计算两个十六进制哈希字符串之间的汉明距离
    """
    if not hash1 or not hash2:
        return 999
    if len(hash1) != len(hash2):
        return 999
    distance = 0
    for i in range(len(hash1)):
        xor_val = int(hash1[i], 16) ^ int(hash2[i], 16)
        while xor_val:
            distance += xor_val & 1
            xor_val >>= 1
    return distance


def find_duplicate_in_album(album_id, phash_val, threshold=None, db_session=None):
    """
    在指定相册中查找与给定 phash 最相似的照片
    返回 (photo, distance) 或 (None, None)
    """
    from ..db import Photo
    if threshold is None:
        threshold = PHASH_DISTANCE_THRESHOLD

    if db_session is None:
        from ..db import db as _db
        db_session = _db.session

    existing_photos = Photo.query.filter_by(album_id=album_id).all()
    if not existing_photos:
        return None, None

    best_match = None
    best_distance = 999

    for photo in existing_photos:
        photo_hash = getattr(photo, 'phash', None)
        if not photo_hash:
            continue
        dist = hamming_distance(phash_val, photo_hash)
        if dist < best_distance:
            best_distance = dist
            best_match = photo
            if best_distance <= threshold:
                break

    if best_match and best_distance <= threshold:
        return best_match, best_distance
    return None, None


def is_duplicate(album_id, phash_val, threshold=None, db_session=None):
    """
    判断是否为疑似重复
    """
    match, dist = find_duplicate_in_album(album_id, phash_val, threshold, db_session)
    return match is not None
