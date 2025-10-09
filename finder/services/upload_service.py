import os
from pathlib import Path
from typing import List, Tuple

from fastapi import UploadFile, HTTPException, status

from finder.utils.files import write_files, delete_files, FileTooLargeError

ALLOWED_EXTENSIONS = set(os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,webp,bmp,tif,tiff").split(","))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))


class UploadService:
    @staticmethod
    async def upload_files(
            target_dir: Path,
            files: List[Tuple[UploadFile, Path]]
    ) -> List[bytes]:
        target_dir.mkdir(parents=True, exist_ok=True)

        paths: List[Tuple[UploadFile, Path]] = []
        for file, filename in files:
            suffix = filename.suffix.lower().lstrip(".")
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported file type: {suffix}.")

            paths.append((file, target_dir / filename))

        try:
            return await write_files(paths, MAX_FILE_SIZE)

        except Exception as e:
            await delete_files([p for _, p in paths])

            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=None if isinstance(e, FileTooLargeError) else "File too large."
            )
