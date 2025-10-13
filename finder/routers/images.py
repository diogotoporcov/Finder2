import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

import numpy as np
import sqlalchemy as sa
from PIL import UnidentifiedImageError
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Response
from fastapi import status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from finder.config import config
from finder.db.models.collection import Collection
from finder.db.models.image import Image
from finder.db.models.image_fingerprint import ImageFingerprint
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService
from finder.services.embedding_service import EmbeddingService
from finder.utils.duplicates import detect_duplicate_sha256, detect_duplicate_phash, detect_duplicate_embedding
from finder.utils.files import load_images_from_bytes, read_files_from_upload_file, write_files_bytes, delete_files, \
    read_file
from finder.utils.hashing import sha256_many, phash_many

router = APIRouter(prefix="/images", tags=["images"])


@dataclass
class FileData:
    uuid: uuid.UUID
    file: UploadFile
    stored_filename: str
    sha256: str
    phash: bytes
    file_content: bytes
    embedding: Optional[np.ndarray] = None


@router.get("/{image_id}", status_code=status.HTTP_200_OK)
async def get_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    image: Optional[Image] = await db.scalar(
        sa.select(Image).where(Image.id == image_id, Image.owner_id == user.id)
    )

    if image is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found, or you do not have permission from the owner to access it."
        )

    image_path = config.STORAGE_PATH / "collections" / str(image.owner_id) / str(image.collection_id) / str(image.stored_filename)
    try:
        bytes_ = await read_file(image_path)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found."
        )

    return Response(content=bytes_, media_type=image.mime_type)


@router.get("/", status_code=status.HTTP_200_OK)
async def get_images(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    result = await db.execute(
        sa.select(Image.id, Collection)
        .join(Collection, Image.collection_id == Collection.id)
        .where(Image.owner_id == user.id)
    )
    rows = result.all()

    collections_map = defaultdict(list)
    for image_id, collection in rows:
        collections_map[str(collection.id)].append(str(image_id))

    return dict(collections_map)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload(
        files: List[UploadFile] = File(...),
        target_collection_id: uuid.UUID | Literal["DEFAULT"] = Query("DEFAULT"),
        detect_duplicates: bool = Query(False),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(AuthService.get_current_user),
        embedder: EmbeddingService = Depends(EmbeddingService.get_instance)
):
    if not files or not files[0].filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were provided.")

    if len(files) > config.MAX_UPLOAD_FILES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Too many files uploaded.")

    if not embedder.is_running():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Upload service is currently not available.")

    for file in files:
        if file.content_type not in config.ALLOWED_MIME_TYPES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' has unsupported type '{file.content_type}'.",
            )

    stmt = sa.select(Collection.id).where(Collection.owner_id == user.id)
    if target_collection_id == "DEFAULT":
        stmt = stmt.where(Collection.is_default.is_(True))
    else:
        stmt = stmt.where(Collection.id == target_collection_id)

    collection_id: uuid.UUID = await db.scalar(stmt)
    if not collection_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found.")

    upload_path = config.STORAGE_PATH / "collections" / str(user.id) / str(collection_id)
    upload_path.mkdir(exist_ok=True, parents=True)

    file_contents = await read_files_from_upload_file(files, config.MAX_FILE_SIZE)

    try:
        pil_images = await load_images_from_bytes(file_contents, [file.filename for file in files])

    except UnidentifiedImageError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Failed to read image: {e}. The file may be corrupted."
        ) from e

    sha256_list = await sha256_many(file_contents)
    phash_list = await phash_many(pil_images, hash_size=8)
    embeddings = await embedder.embed(pil_images)

    file_datas: List[FileData] = []
    for file, pil_image, sha256, phash, content, embedding in zip(
            files, pil_images, sha256_list, phash_list, file_contents, embeddings):
        uuid_ = uuid.uuid4()
        file_datas.append(FileData(
            uuid=uuid_,
            file=file,
            stored_filename=f"{uuid_}{Path(file.filename).suffix}",
            sha256=sha256,
            phash=phash,
            embedding=embedding,
            file_content=content
        ))

    images: List[Image] = []
    image_fingerprints: List[ImageFingerprint] = []
    for data in file_datas:
        images.append(
            Image(
                id=data.uuid,
                owner_id=user.id,
                collection_id=collection_id,
                stored_filename=data.stored_filename,
                original_filename=data.file.filename,
                mime_type=data.file.content_type,
                size_bytes=len(data.file_content),
            )
        )
        image_fingerprints.append(
            ImageFingerprint(
                image_id=data.uuid,
                sha256=data.sha256,
                phash=int.from_bytes(data.phash, signed=True),
                embedding=data.embedding,
            )
        )

    try:
        db.add_all(images)
        db.add_all(image_fingerprints)
        await db.flush()

        duplicate_map = {}
        if detect_duplicates:
            remaining = []
            for data in file_datas:
                dup = (
                        await detect_duplicate_sha256(db, user.id, collection_id, data.uuid)
                        or await detect_duplicate_phash(db, user.id, collection_id, data.uuid)
                        or await detect_duplicate_embedding(db, user.id, collection_id, data.uuid)
                )

                if dup:
                    duplicate_map[str(data.uuid)] = str(dup)

                else:
                    remaining.append(data)

            file_datas = remaining

        if not file_datas:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "All files already exist in the target collection.", "duplicates": duplicate_map}
            )

        for image in images:
            if str(image.id) in duplicate_map:
                db.expunge(image)

        for image_fingerprint in image_fingerprints:
            if str(image_fingerprint.image_id) in duplicate_map:
                db.expunge(image_fingerprint)

        await db.commit()

        await write_files_bytes([
            (data.file_content, upload_path / data.stored_filename)
            for data in file_datas
        ])

        if detect_duplicates and duplicate_map:
            return {
                "status": "partial",
                "files": [data.uuid for data in file_datas],
                "duplicates": duplicate_map
            }

        return {
            "status": "created",
            "files": [data.uuid for data in file_datas]
        }

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        await delete_files([upload_path / data.stored_filename for data in file_datas])
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR) from e


class ImageUpdate(BaseModel):
    tags: Optional[List[str]] = None


@router.patch("/{image_id}")
async def update_image(
    image_id: uuid.UUID,
    image_update: ImageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    image = await db.scalar(
        sa.select(Image).where(
            Image.id == image_id,
            Image.owner_id == user.id
        )
    )
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    if image_update.tags is not None:
        image.tags = image_update.tags

    await db.commit()
    await db.refresh(image)
    return image


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    image = await db.scalar(
        sa.select(Image).where(
            Image.id == image_id,
            Image.owner_id == user.id
        )
    )
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    await db.delete(image)
    await db.commit()
