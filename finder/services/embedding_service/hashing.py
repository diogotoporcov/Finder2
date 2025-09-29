import hashlib
import io

import imagehash
from PIL import Image


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phash64(img_bytes: bytes, hash_size=8) -> int:
    image = Image.open(io.BytesIO(img_bytes))
    image_phash = imagehash.phash(image, hash_size=hash_size)
    return int(str(image_phash), 16)
