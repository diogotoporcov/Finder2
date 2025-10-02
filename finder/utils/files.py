import asyncio
import io
from pathlib import Path
from typing import Tuple, List

import aiofiles
import aiofiles.os
from PIL import Image
from fastapi import UploadFile


class FileTooLargeError(Exception):
    pass


async def write_file(file: UploadFile, path: Path, max_file_size: int) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)

    data = bytearray()
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            await f.write(chunk)
            if len(data) > max_file_size:
                await f.close()
                path.unlink(missing_ok=True)
                raise FileTooLargeError(f"File exceeds max file size: '{file.filename}'")

    return bytes(data)


async def write_files(files: List[Tuple[UploadFile, Path]], max_file_size: int) -> List[bytes]:
    tasks = [write_file(file, path, max_file_size) for file, path in files]
    return await asyncio.gather(*tasks)


async def delete_file(path: Path):
    try:
        await aiofiles.os.remove(path)

    except FileNotFoundError:
        pass


async def delete_files(paths: List[Path]):
    await asyncio.gather(*[delete_file(p) for p in paths])


async def load_image_from_bytes(b: bytes) -> Image.Image:
    return await asyncio.to_thread(Image.open, io.BytesIO(b))


async def load_images_from_bytes(bytes_list: List[bytes]) -> List[Image.Image]:
    return await asyncio.gather(*(load_image_from_bytes(b) for b in bytes_list))
