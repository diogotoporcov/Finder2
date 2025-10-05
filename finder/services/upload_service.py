import os
import uuid
from pathlib import Path
from typing import List, Tuple

from fastapi import UploadFile, HTTPException, status

from finder.utils.files import write_files, delete_files, FileTooLargeError

ALLOWED_EXTENSIONS = set(os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,webp,bmp,tif,tiff").split(","))
TMP_ROOT = Path(os.getenv("TMP_ROOT", "tmp/uploads"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))


class UploadService:
    @staticmethod
    async def upload_files(
            session_id: uuid.UUID,
            files: List[UploadFile],
            filenames: List[Path]
    ) -> List[bytes]:
        if len(files) != len(filenames):
            raise ValueError("Length of files and names must match.")

        uploads_path = TMP_ROOT / str(session_id)
        uploads_path.mkdir(parents=True, exist_ok=True)

        paths: List[Tuple[UploadFile, Path]] = []
        for file, filename in zip(files, filenames):
            suffix = filename.suffix.lower().lstrip(".")
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported file type: {suffix}.")

            paths.append((file, uploads_path/filename))

        try:
            return await write_files(paths, MAX_FILE_SIZE)

        except Exception as e:
            await delete_files(list(uploads_path.iterdir()))
            uploads_path.rmdir()

            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=None if isinstance(e, FileTooLargeError) else "File too large."
            )
