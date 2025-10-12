import os
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

import PIL.Image
import humanfriendly
import numpy as np
import sqlalchemy as sa
from bs4 import BeautifulSoup
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Response
from fastapi import status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from finder.db.models.collection import Collection
from finder.db.models.image import Image
from finder.db.models.image_fingerprint import ImageFingerprint
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService
from finder.services.duplicate_service import DuplicateService
from finder.services.embedding_service import EmbeddingService
from finder.utils.files import load_images_from_bytes, read_files_from_upload_file, write_files_bytes, delete_files, \
    read_file
from finder.utils.hashing import sha256_many, phash_many

router = APIRouter(prefix="/images", tags=["images"])

STORAGE_PATH = Path("storage/collections")
ALLOWED_EXTENSIONS = set(os.getenv("ALLOWED_EXTENSIONS").split(","))
MAX_FILE_SIZE = humanfriendly.parse_size(os.getenv("MAX_FILE_SIZE"))
MAX_FILES = int(os.getenv("MAX_UPLOAD_FILES"))


@dataclass
class FileData:
    uuid: uuid.UUID
    file: UploadFile
    stored_filename: str
    pil_image: PIL.Image.Image
    sha256: str
    phash: bytes
    file_content: bytes
    embedding: Optional[np.ndarray] = None


@router.get("/{image_id}", status_code=status.HTTP_200_OK)
async def get_image(
        image_id: uuid.UUID,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    image: Optional[Image] = (
        db.query(Image)
        .filter(Image.id == image_id, Image.owner_id == user.id)
        .first()
    )

    if image is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found, or you do not have permission from the owner to access it."
        )

    try:
        image_path = STORAGE_PATH / str(image.owner_id) / str(image.collection_id) / str(image.stored_filename)
        bytes_ = await read_file(image_path)
    except (FileNotFoundError, PermissionError) as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="The requested file was not found."
        ) from e

    return Response(content=bytes_, media_type=image.mime_type)


@router.get("/", status_code=status.HTTP_200_OK)
async def get_images(
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
) -> HTMLResponse:
    rows = (
        db.execute(
            sa.select(Image.id, Collection)
            .join(Collection, Image.collection_id == Collection.id)
            .where(Image.owner_id == user.id)
        )
        .all()
    )

    collections_map = defaultdict(list)
    for image_id, collection in rows:
        collections_map[collection].append(image_id)

    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    body = soup.body

    title = soup.new_tag("h1")
    title.string = "Images"
    body.append(title)

    for collection, image_ids in collections_map.items():
        h2 = soup.new_tag("h2")
        h2.string = collection.name
        body.append(h2)

        ul = soup.new_tag("ul")
        for image_id in image_ids:
            li = soup.new_tag("li")
            a = soup.new_tag("a", href=f"/{image_id}")
            a.string = str(image_id)
            li.append(a)
            ul.append(li)
        body.append(ul)

    return HTMLResponse(content=str(soup))


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload(
        files: List[UploadFile] = File(...),
        target_collection: uuid.UUID | Literal["DEFAULT"] = Query("DEFAULT"),
        detect_duplicates: bool = Query(False),
        use_deepsearch: bool = Query(False),
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user),
        embedder: EmbeddingService = Depends(EmbeddingService.get_instance)
):
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No files were provided.")

    if len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Too many files uploaded.")

    if use_deepsearch and not embedder.is_running():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Deepsearch service is currently not available.")

    query = db.query(Collection.id).filter(Collection.owner_id == user.id)
    if target_collection == "DEFAULT":
        query = query.filter(Collection.is_default.is_(True))
    else:
        query = query.filter(Collection.id == target_collection)

    collection_id: uuid.UUID = query.scalar()
    if not collection_id or not isinstance(collection_id, uuid.UUID):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found.")

    upload_path = STORAGE_PATH / str(user.id) / str(collection_id)

    file_contents = await read_files_from_upload_file(files, MAX_FILE_SIZE)
    pil_images = await load_images_from_bytes(file_contents)

    sha256_list = await sha256_many(file_contents)
    phash_list = await phash_many(pil_images, hash_size=8)

    file_datas: List[FileData] = []
    for file, pil_image, sha256, phash, content in zip(files, pil_images, sha256_list, phash_list, file_contents):
        uuid_ = uuid.uuid4()
        file_datas.append(FileData(
            uuid=uuid_,
            file=file,
            stored_filename=f"{uuid_}{Path(file.filename).suffix}",
            pil_image=pil_image,
            sha256=sha256,
            phash=phash,
            file_content=content
        ))

    duplicate_map = {}
    if detect_duplicates:
        for data in list(file_datas):
            duplicated_sha = DuplicateService.detect_duplicate_sha256(db, user.id, collection_id, data.uuid)
            duplicated_phash = None
            if duplicated_sha is None:
                duplicated_phash = DuplicateService.detect_duplicate_phash(db, user.id, collection_id, data.uuid)

            found = duplicated_sha or duplicated_phash
            if found:
                duplicate_map[str(data.uuid)] = str(found)
                file_datas.remove(data)

    embeddings = await embedder.embed([data.pil_image for data in file_datas])
    for data, embedding in zip(file_datas, embeddings):
        data.embedding = embedding

    if detect_duplicates:
        for data in list(file_datas):
            duplicated_emb = DuplicateService.detect_duplicate_embedding(db, user.id, collection_id, data.uuid)

            if duplicated_emb:
                duplicate_map[str(data.uuid)] = str(duplicated_emb)
                file_datas.remove(data)

    if not file_datas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "All files already exist in the target collection.", "duplicates": duplicate_map}
        )

    images: List[Image] = []
    image_embeddings: List[ImageFingerprint] = []
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

        image_embeddings.append(
            ImageFingerprint(
                image_id=data.uuid,
                sha256=data.sha256,
                phash=int.from_bytes(data.phash, signed=True),
                embedding=data.embedding,
            )
        )

    try:
        db.add_all(images)
        db.add_all(image_embeddings)
        db.commit()
        await write_files_bytes([
            (data.file_content, upload_path / data.stored_filename)
            for data in file_datas
        ])
    except Exception as e:
        db.rollback()
        await delete_files([upload_path / data.stored_filename for data in file_datas])
        print(e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR) from e

    if duplicate_map:
        return {
            "status": "partial",
            "duplicates": duplicate_map
        }

    return {"status": "created"}


@router.patch("/{image_id}")
def update_image(
        image_id: uuid.UUID,
        tags: List[str],
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    image = db.scalar(
        sa.select(Image)
        .where(
            Image.id == image_id,
            Image.owner_id == user.id
        )
    )
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    image.tags = tags
    db.commit()
    db.refresh(image)
    return image


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
        image_id: uuid.UUID,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    image = db.scalar(
        sa.select(Image)
        .where(
            Image.id == image_id,
            Image.owner_id == user.id
        )
    )
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    db.delete(image)
    db.commit()
    return None
