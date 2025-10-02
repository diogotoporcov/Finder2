import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, HTTPException, Request, Depends, File
from sqlalchemy.orm import Session
from starlette import status
from starlette.responses import JSONResponse
from starlette.status import HTTP_201_CREATED

from finder.db.models.image import Image
from finder.db.models.upload_session import UploadSession, UploadSessionImage
from finder.db.session import get_db
from finder.services.embedding_service import EmbeddingService
from finder.utils.files import FileTooLargeError, delete_files, write_files

router = APIRouter()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}
TMP_ROOT = Path("tmp") / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024


@dataclass
class UploadItem:
    upload_file: UploadFile
    path: Path
    image: Image
    session_link: UploadSessionImage


@router.post("/uploads")
async def upload_files(
        request: Request,
        files: List[UploadFile] = File(...),
        db: Session = Depends(get_db),
) -> JSONResponse:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    embedder: EmbeddingService = request.app.state.embedder
    if not (embedder and embedder.is_running()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload service not available.",
        )

    session_id = uuid.uuid4()
    upload_session = UploadSession(id=session_id)

    uploads_path = TMP_ROOT / str(session_id)

    items: List[UploadItem] = []

    for file in files:
        suffix = Path(file.filename).suffix.lower().lstrip(".")
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: '{suffix}' ({file.filename})"
            )

        image_id = uuid.uuid4()
        filename = f"{image_id}.{suffix}"
        path = uploads_path / filename

        image = Image(
            id=image_id,
            stored_filename=filename,
            original_filename=file.filename,
            mime_type=file.content_type
        )
        session_link = UploadSessionImage(
            upload_session_id=session_id,
            image_id=image_id
        )

        items.append(UploadItem(
            upload_file=file,
            path=path,
            image=image,
            session_link=session_link
        ))

    try:
        file_bytes_list = await write_files(
            [(item.upload_file, item.path) for item in items],
            MAX_FILE_SIZE
        )

        results = await embedder.embed(file_bytes_list)

        for item, result, bytes_ in zip(items, results, file_bytes_list):
            item.image.size_bytes = len(bytes_)
            item.image.sha256 = result.sha256
            item.image.phash = result.phash
            item.image.embedding = result.embedding

        db.add(upload_session)
        db.add_all([item.image for item in items])
        db.add_all([item.session_link for item in items])
        db.commit()

    except FileTooLargeError as e:
        await delete_files([item.path for item in items])
        uploads_path.rmdir()

        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload failed: {str(e)}"
        ) from e

    except Exception as e:
        db.rollback()

        await delete_files([item.path for item in items])
        uploads_path.rmdir()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed for unknown reason, please contact an admin. Request ID: {session_id}"
        ) from e

    return JSONResponse(
        {"upload_session_id": str(session_id)},
        status_code=HTTP_201_CREATED
    )
