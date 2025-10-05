import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from finder.db.models.image import Image
from finder.db.models.upload_session import UploadSession, UploadSessionImage
from finder.db.models.user import User
from finder.services.embedding_service import EmbeddingService
from finder.utils.files import write_files, delete_files, FileTooLargeError

ALLOWED_EXTENSIONS = set(os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,webp,gif,bmp,tif,tiff").split(","))
TMP_ROOT = Path(os.getenv("TMP_ROOT", "tmp/uploads"))
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))


class UploadService:
    @dataclass
    class UploadItem:
        upload_file: UploadFile
        path: Path
        image: Image
        session_link: UploadSessionImage

    @staticmethod
    async def upload_files(
            files: List[UploadFile],
            user: User,
            db: Session,
            embedder: EmbeddingService,
    ) -> str:
        if not files:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were provided.")

        if not (embedder and embedder.is_running()):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Upload service unavailable.")

        session_id = uuid.uuid4()
        upload_session = UploadSession(id=session_id, owner_id=user.id)
        uploads_path = TMP_ROOT / str(session_id)
        uploads_path.mkdir(parents=True, exist_ok=True)

        items: List[UploadService.UploadItem] = []
        for f in files:
            suffix = Path(f.filename).suffix.lower().lstrip(".")
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported file type: {suffix}.")

            image_id = uuid.uuid4()
            filename = f"{image_id}.{suffix}"
            path = uploads_path / filename

            image = Image(
                id=image_id,
                owner_id=user.id,
                stored_filename=filename,
                original_filename=f.filename,
                mime_type=f.content_type,
            )

            link = UploadSessionImage(upload_session_id=session_id, image_id=image_id)
            items.append(UploadService.UploadItem(f, path, image, link))

        try:
            file_bytes = await write_files([(i.upload_file, i.path) for i in items], MAX_FILE_SIZE)
            results = await embedder.embed(file_bytes)

            for item, res, b in zip(items, results, file_bytes):
                item.image.size_bytes = len(b)
                item.image.sha256 = res.sha256
                item.image.phash = res.phash
                item.image.embedding = res.embedding

            db.add(upload_session)
            db.add_all([i.image for i in items])
            db.add_all([i.session_link for i in items])
            db.commit()

            return str(session_id)

        except FileTooLargeError:
            await delete_files([i.path for i in items])
            uploads_path.rmdir()

            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large.")

        except Exception:
            db.rollback()
            await delete_files([i.path for i in items])
            uploads_path.rmdir()

            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
