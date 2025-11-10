import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Dict

import numpy as np
import sqlalchemy as sa
from PIL import UnidentifiedImageError
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Response
from fastapi import status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import config
from src.db.models.collection import Collection
from src.db.models.duplicates import ImageDuplicate
from src.db.models.image import Image
from src.db.models.image_fingerprint import ImageFingerprint
from src.db.models.user import User
from src.db.session import get_db
from src.services.auth_service import AuthService
from src.services.embedding_service import EmbeddingService
from src.utils.duplicates import find_duplicate_sha256, find_duplicate_phash, find_duplicate_embedding
from src.utils.files import load_images_from_bytes, read_files_from_upload_file, write_files_bytes, delete_files, \
    read_file
from src.utils.hashing import sha256_many, phash_many

router = APIRouter(
    prefix="/images",
    tags=["Images"],
)


@dataclass
class FileData:
    """Internal file metadata used during upload."""

    uuid: uuid.UUID
    file: UploadFile
    stored_filename: str
    sha256: str
    phash: bytes
    file_content: bytes
    embedding: Optional[np.ndarray] = None


class ImagesOut(BaseModel):
    """Mapping of collection IDs to image IDs."""

    __root__: Dict[uuid.UUID, List[uuid.UUID]] = Field(
        ...,
        description="Map of collection ID to list of image IDs.",
        examples=[{
            "0a47cd8a-6596-48f7-961e-0d657345e343": [
                "3384ac64-82c1-4163-838f-ca3c49fe7fb3",
                "bd9c464d-0111-4a11-81f7-99a41cbc0e5a"
            ]
        }],
    )


class ImageOut(BaseModel):
    """Image details."""

    id: uuid.UUID = Field(
        ...,
        description="Image ID.",
    )
    owner_id: uuid.UUID = Field(
        ...,
        description="Image ID.",
    )

    collection_id: uuid.UUID = Field(
        ...,
        description="Collection ID.",
    )

    tags: List[str] = Field(
        ...,
        description="Image tags.",
    )

    model_config = ConfigDict(
        from_attributes=True
    )


class ImageUpdate(BaseModel):
    """Payload to update image metadata."""

    tags: Optional[List[str]] = Field(
        default=None,
        description="New list of tags.",
        examples=[["machinery", "factory"]],
    )


class UploadOut(BaseModel):
    """Result of image upload."""

    files: Optional[List[uuid.UUID]] = Field(
        default=None,
        description="Uploaded image IDs.",
    )

    duplicates: Optional[Dict[uuid.UUID, uuid.UUID]] = Field(
        default=None,
        description="Detected duplicates as `new_image_id: original_image_id`.",
    )


@router.get(
    "/{image_id}",
    status_code=status.HTTP_200_OK,
    summary="Get image",
    description="Retrieve an image owned by the authenticated user.",
    responses={
        200: {"description": "Image returned as binary content."},
        401: {"description": "Unauthorized."},
        404: {"description": "Image not found or not accessible."},
    },
)
async def get_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> Response:
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


@router.get(
    "/",
    response_model=ImagesOut,
    status_code=status.HTTP_200_OK,
    summary="List images",
    description="List all images grouped by collection for the authenticated user.",
    responses={
        200: {"description": "Images listed by collection."},
        401: {"description": "Unauthorized."},
    },
)
async def get_images(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> ImagesOut:
    """
    Return the image binary for the authenticated user.
    """

    result = await db.execute(
        sa.select(Image.id, Collection)
        .join(Collection, Image.collection_id == Collection.id)
        .where(Image.owner_id == user.id)
    )
    rows = result.all()

    collections_map = defaultdict(list)
    for image_id, collection in rows:
        collections_map[str(collection.id)].append(str(image_id))

    return ImagesOut(__root__=dict(collections_map))


@router.post(
    "/",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload images",
    description=(
        "Upload one or more images to a collection. "
        "`target_collection_id` can be a collection UUID or `DEFAULT`. "
        "Duplicate detection may be applied depending on configuration."
    ),
    responses={
        201: {"description": "Images uploaded."},
        400: {"description": "No files, invalid files, or bad input."},
        401: {"description": "Unauthorized."},
        413: {"description": "Too many files or files too large."},
        415: {"description": "Unsupported media type."},
        503: {"description": "Upload service not available."},
    },
)
async def upload(
    files: List[UploadFile] = File(..., description="Images to upload."),
    target_collection_id: uuid.UUID | Literal["DEFAULT"] = Query(
        "DEFAULT",
        description="Target collection ID or `DEFAULT` for the user's default collection.",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
    embedder: EmbeddingService = Depends(EmbeddingService.get_instance),
) -> UploadOut:
    """
    Upload images to the specified collection and return created IDs and detected duplicates.
    """

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

        duplicate_map: Dict[uuid.UUID, uuid.UUID] = {}
        for data in file_datas:
            dupe = (
                    await find_duplicate_sha256(db, user.id, collection_id, data.uuid)
                    or await find_duplicate_phash(db, user.id, collection_id, data.uuid)
                    or await find_duplicate_embedding(db, user.id, collection_id, data.uuid)
            )

            if dupe:
                duplicate_map[data.uuid] = dupe

        if duplicate_map:
            dupes: List[ImageDuplicate] = []
            for dupe_id, original_id in duplicate_map.items():
                dupes.append(ImageDuplicate(
                    image_id=dupe_id,
                    original_image_id=original_id
                ))

            db.add_all(dupes)

        await db.commit()

        await write_files_bytes([
            (data.file_content, upload_path / data.stored_filename)
            for data in file_datas
        ])

        if duplicate_map:
            return UploadOut(
                files=[data.uuid for data in file_datas],
                duplicates=duplicate_map
            )

        else:
            return UploadOut(
                files=[data.uuid for data in file_datas]
            )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        await delete_files([upload_path / data.stored_filename for data in file_datas])
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR) from e


@router.patch(
    "/{image_id}",
    response_model=ImageOut,
    status_code=status.HTTP_200_OK,
    summary="Update image",
    description="Update image metadata.",
    responses={
        200: {"description": "Image updated."},
        401: {"description": "Unauthorized."},
        404: {"description": "Image not found."},
    },
)
async def update_image(
    image_id: uuid.UUID,
    image_update: ImageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> ImageOut:
    """
    Update tags for an image owned by the authenticated user.
    """

    image: Image = await db.scalar(
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
    return ImageOut.model_validate(image)


@router.delete(
    "/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete image",
    description="Delete an image owned by the authenticated user.",
    responses={
        204: {"description": "Image deleted."},
        401: {"description": "Unauthorized."},
        404: {"description": "Image not found."},
    },
)
async def delete_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> None:
    """
    Delete an image owned by the authenticated user.
    """

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
