import uuid
from typing import List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from finder.db.models.collection import Collection
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService

router = APIRouter(prefix="/collections", tags=["collections"])


class CollectionCreate(BaseModel):
    name: str
    tags: Optional[List[str]] = None


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_collection(
    collection_data: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    existing = await db.scalar(
        sa.select(Collection).where(
            Collection.owner_id == user.id,
            Collection.name == collection_data.name
        )
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Collection with this name already exists."
        )

    collection = Collection(
        owner_id=user.id,
        name=collection_data.name,
        tags=collection_data.tags or []
    )

    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


@router.patch("/{collection_id}", status_code=status.HTTP_200_OK)
async def update_collection(
    collection_id: uuid.UUID,
    collection_update: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    collection = await db.scalar(
        sa.select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found.")
    if collection_update.name == "DEFAULT":
        raise HTTPException(status_code=400, detail="Cannot rename collection to DEFAULT.")

    if collection_update.name is not None:
        collection.name = collection_update.name
    if collection_update.tags is not None:
        collection.tags = collection_update.tags

    await db.commit()
    await db.refresh(collection)
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    collection = await db.scalar(
        sa.select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found.")

    await db.delete(collection)
    await db.commit()
    return None
