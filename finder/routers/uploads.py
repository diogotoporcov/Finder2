import uuid
from itertools import repeat
from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, UploadFile, File, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette import status
from starlette.status import HTTP_200_OK

from finder.db.models.image import Image
from finder.db.models.upload_session import UploadSession, UploadSessionImage
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService
from finder.services.embedding_service import EmbeddingService
from finder.services.upload_service import UploadService
from finder.utils.files import load_images_from_bytes
from finder.utils.hashing import generate_sha256_many, generate_phash_many

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadOut(BaseModel):
    upload_session_id: str


@router.post("/", response_model=UploadOut)
async def upload_files(
        session_id: uuid.UUID = Depends(uuid.uuid4),
        files: List[UploadFile] = File(...),
        enable_deepsearch: bool = Query(False, description="Enable deep search"),
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user),
        embedder: EmbeddingService = Depends(EmbeddingService.get_instance)
) -> UploadOut:
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were provided.")

    if enable_deepsearch and not embedder.is_running():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Deepsearch service is currently not available.")

    file_ids = [uuid.uuid4() for _ in files]
    filenames = [
        Path(file.filename).with_stem(str(id_))
        for file, id_
        in zip(files, file_ids)
    ]

    bytes_list = await UploadService.upload_files(session_id, files, filenames)
    pil_images = await load_images_from_bytes(bytes_list)

    sha256_list = await generate_sha256_many(bytes_list)
    phash_list = await generate_phash_many(pil_images, hash_size=8)
    embeds = (
        await embedder.embed(pil_images)
        if enable_deepsearch
        else repeat(None, len(files))
    )

    upload_session = UploadSession(id=session_id, owner_id=user.id)
    images, us_images = [], []

    for id_, file, filename, sha256, phash, embedding, bytes_ in zip(
            file_ids, files, filenames, sha256_list, phash_list, embeds, bytes_list
    ):
        images.append(
            Image(
                id=id_,
                owner_id=user.id,
                stored_filename=filename,
                original_filename=file.filename,
                mime_type=file.content_type,
                size_bytes=len(bytes_),
                sha256=sha256,
                phash=phash,
                embedding=embedding
            )
        )

        us_images.append(
            UploadSessionImage(
                upload_session_id=session_id,
                image_id=id_
            )
        )

    try:
        db.add(upload_session)
        db.add_all(images)
        db.add_all(us_images)
        db.commit()

        return UploadOut(upload_session_id=str(session_id))

    except Exception:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)


class UploadPayload(BaseModel):
    upload_id: uuid.UUID
    collection_id: uuid.UUID | Literal["DEFAULT"]


@router.post("/save", status_code=HTTP_200_OK)
async def save_upload(payload: UploadPayload):
    # TODO
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
