import uuid
from typing import List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.collection import Collection
from src.db.models.user import User
from src.db.session import get_db
from src.services.auth_service import AuthService

router = APIRouter(
    prefix="/collections",
    tags=["Collections"],
)


class CollectionCreate(BaseModel):
    """Payload to create a new collection."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Collection name.",
        examples=["Cats"],
    )

    tags: Optional[List[str]] = Field(
        default=None,
        description="Optional list of tags.",
        examples=[["sphynx", "2025", "tabby"]],
    )


class CollectionOut(BaseModel):
    """Collection details."""

    id: uuid.UUID = Field(
        ...,
        description="Collection ID.",
    )

    owner_id: uuid.UUID = Field(
        ...,
        description="Collection Owner ID.",
    )

    name: str = Field(
        ...,
        description="Collection name.",
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Collection tags.",
    )

    model_config = ConfigDict(
        from_attributes=True
    )


class CollectionUpdate(BaseModel):
    """Payload to update an existing collection."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="New collection name.",
        examples=["Dogs"],
    )

    tags: Optional[List[str]] = Field(
        default=None,
        description="New list of tags.",
        examples=[["dachshund", "cute", "2013"]],
    )


@router.post(
    "/",
    response_model=CollectionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create collection",
    description="Create a new collection for the authenticated user.",
    responses={
        status.HTTP_201_CREATED: {"description": "Collection created."},
        status.HTTP_400_BAD_REQUEST: {"description": "Collection with this name already exists."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized."},
    },
)
async def create_collection(
    collection_data: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> CollectionOut:
    """
    Create a collection owned by the authenticated user.

    `name` must be unique per user.
    """

    existing = await db.scalar(
        sa.select(Collection).where(
            Collection.owner_id == user.id,
            Collection.name == collection_data.name
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    return CollectionOut.model_validate(collection)


@router.patch(
    "/{collection_id}",
    status_code=status.HTTP_200_OK,
    summary="Update collection",
    description="Update name or tags of an existing collection.",
    responses={
        status.HTTP_200_OK: {"description": "Collection updated."},
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid update (for example, forbidden name)."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized."},
        status.HTTP_404_NOT_FOUND: {"description": "Collection not found."},
    },
)
async def update_collection(
    collection_id: uuid.UUID,
    collection_update: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> CollectionOut:
    """
    Update a collection owned by the authenticated user.
    """

    collection = await db.scalar(
        sa.select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collection not found.")
    if collection_update.name == "DEFAULT":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot rename collection to DEFAULT.")

    if collection_update.name is not None:
        collection.name = collection_update.name

    if collection_update.tags is not None:
        collection.tags = collection_update.tags

    await db.commit()
    await db.refresh(collection)
    return CollectionOut(
        id=collection.id,
        owner_id=collection.owner_id,
        name=collection.name,
        tags=collection.tags
    )


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete collection",
    description="Delete a collection owned by the authenticated user.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Collection deleted."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized."},
        status.HTTP_404_NOT_FOUND: {"description": "Collection not found."},
    },
)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> None:
    collection = await db.scalar(
        sa.select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collection not found.")

    await db.delete(collection)
    await db.commit()
