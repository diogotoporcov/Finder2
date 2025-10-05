import asyncio
import os
from typing import Tuple, List

import numpy as np
from PIL import Image

CLIP_IMG_SIZE = int(os.getenv("CLIP_IMG_SIZE", 224))
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


def preprocess_image(image: Image.Image, img_size: Tuple[int, int] = (CLIP_IMG_SIZE, CLIP_IMG_SIZE)) -> np.ndarray:
    image = image.convert("RGB")
    img = image.resize(img_size, Image.Resampling.BICUBIC)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - CLIP_MEAN) / CLIP_STD
    arr = np.transpose(arr, (2, 0, 1))
    return arr


async def preprocess_many(images: List[Image.Image]) -> np.ndarray[np.float32]:
    tasks = [asyncio.to_thread(preprocess_image, img) for img in images]
    arrays = await asyncio.gather(*tasks)
    return np.stack(arrays, axis=0).astype(np.float32)
