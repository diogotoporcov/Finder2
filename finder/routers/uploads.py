import uuid
from itertools import repeat
from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette import status

from finder.db.models.collection import Collection
from finder.db.models.image import Image
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService
from finder.services.duplicate_service import DuplicateService
from finder.services.embedding_service import EmbeddingService
from finder.services.upload_service import UploadService
from finder.utils.files import load_images_from_bytes
from finder.utils.hashing import generate_sha256_many, generate_phash_many

router = APIRouter(prefix="/uploads", tags=["uploads"])


STORAGE_PATH = Path("storage/collections")


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload(
        files: List[UploadFile] = File(...),
        collection_id: uuid.UUID | Literal["DEFAULT"] = Query("DEFAULT"),
        detect_duplicates: bool = Query(False),
        use_deepsearch: bool = Query(False),

        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user),
        embedder: EmbeddingService = Depends(EmbeddingService.get_instance)
):
    # TODO: SEPARAR ESCREVER E LER OS DADOS, CANCELAR ESCRITA SE DUPLICATA.
    # TODO: SEPARAR ESCREVER E LER OS DADOS, CANCELAR ESCRITA SE DUPLICATA.
    # TODO: SEPARAR ESCREVER E LER OS DADOS, CANCELAR ESCRITA SE DUPLICATA.
    # TODO: SEPARAR ESCREVER E LER OS DADOS, CANCELAR ESCRITA SE DUPLICATA.

    if not files:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No files were provided."
        )

    if use_deepsearch and not embedder.is_running():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Deepsearch service is currently not available."
        )

    file_ids = [uuid.uuid4() for _ in files]
    filenames = [
        Path(file.filename).with_stem(str(id_))
        for file, id_
        in zip(files, file_ids)
    ]

    query = db.query(Collection.id).filter(Collection.owner_id == user.id)

    if collection_id == "DEFAULT":
        query = query.filter(Collection.is_default.is_(True))

    else:
        query = query.filter(Collection.id == collection_id)

    collection_id: uuid.UUID = query.scalar()

    if not collection_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection not found.")

    upload_path = STORAGE_PATH / str(user.id) / str(collection_id)

    bytes_list = await UploadService.upload_files(upload_path, [(file, name) for file, name in zip(files, filenames)])
    pil_images = await load_images_from_bytes(bytes_list)

    sha256_list = await generate_sha256_many(bytes_list)
    phash_list = await generate_phash_many(pil_images, hash_size=8)
    embeddings = (
        await embedder.embed(pil_images)
        if use_deepsearch
        else repeat(None, len(files))
    )

    images: List[Image] = []
    for id_, file, filename, sha256, phash, embedding, bytes_ in zip(
            file_ids, files, filenames, sha256_list, phash_list, embeddings, bytes_list
    ):
        if detect_duplicates:
            duplicate = DuplicateService.detect_duplicate(db, user.id, collection_id, sha256, phash)
            print(bool(duplicate))
            if duplicate:
                continue

        images.append(
            Image(
                id=id_,
                owner_id=user.id,
                collection_id=collection_id,
                stored_filename=str(filename),
                original_filename=file.filename,
                mime_type=file.content_type,
                size_bytes=len(bytes_),
                sha256=sha256,
                phash=int.from_bytes(phash, byteorder="big", signed=True),
                embedding=embedding
            )
        )

    try:
        db.add_all(images)
        db.commit()

    except Exception as e:
        db.rollback()
        print(e)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
