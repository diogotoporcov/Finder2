import asyncio
import hashlib
from typing import List

import imagehash
from PIL import Image


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def phash(image: Image.Image, hash_size: int = 8) -> bytes:
    ih = imagehash.phash(image, hash_size=hash_size)
    return bytes.fromhex(str(ih))


async def generate_sha256_many(data_list: List[bytes]) -> List[str]:
    tasks = [asyncio.to_thread(sha256_bytes, b) for b in data_list]
    return await asyncio.gather(*tasks)


async def generate_phash_many(images: List[Image.Image], hash_size: int = 8) -> List[bytes]:
    tasks = [asyncio.to_thread(phash, img, hash_size) for img in images]
    return await asyncio.gather(*tasks)
