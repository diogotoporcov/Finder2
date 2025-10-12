import asyncio
import io
import os
import shutil
from pathlib import Path
from typing import Tuple, List, Optional

import aiofiles
import aiofiles.os
from PIL import Image
from fastapi import UploadFile


class FileTooLargeError(Exception):
    pass


SEM = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_IO")))


async def read_file_from_upload_file(file: UploadFile, max_file_size: int) -> bytes:
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > max_file_size:
            raise FileTooLargeError(f"File exceeds max file size: '{file.filename}'")

    return bytes(data)


async def read_files_from_upload_file(files: List[UploadFile], max_file_size: int) -> List[bytes]:
    tasks = [read_file_from_upload_file(file, max_file_size) for file in files]
    return await asyncio.gather(*tasks)


async def write_file_bytes(data: bytes, path: Path) -> None:
    async with SEM:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)


async def write_files_bytes(data_list: List[Tuple[bytes, Path]]) -> None:
    tasks = [write_file_bytes(data, path) for data, path in data_list]
    await asyncio.gather(*tasks)


async def write_file(file: UploadFile, path: Path, max_file_size: int) -> bytes:
    async with SEM:
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


async def delete_file(path: Path) -> bool:
    async with SEM:
        try:
            await aiofiles.os.remove(path)
            return True
        except FileNotFoundError:
            return True
        except Exception:
            return False


async def delete_files(paths: List[Path]) -> List[bool]:
    return await asyncio.gather(*(delete_file(p) for p in paths))


async def load_image_from_bytes(b: bytes) -> Image.Image:
    async with SEM:
        return await asyncio.to_thread(Image.open, io.BytesIO(b))


async def load_images_from_bytes(bytes_list: List[bytes]) -> List[Image.Image]:
    return await asyncio.gather(*(load_image_from_bytes(b) for b in bytes_list))


async def move_file(src: Path, dst: Path):
    async with SEM:
        await asyncio.to_thread(shutil.move, src, dst)


async def move_files(files, dest_dir):
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    tasks = [move_file(f, Path(dest_dir) / f.name) for f in files]
    await asyncio.gather(*tasks)


async def read_file(path: Path) -> Optional[bytes]:
    async with SEM:
        async with aiofiles.open(path, "rb") as f:
            return await f.read()
