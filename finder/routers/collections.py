import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from finder.db.models.collection import Collection
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_collection(
        name: str,
        tags: Optional[List[str]] = None,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    existing = db.scalar(
        sa.select(Collection)
        .where(
            Collection.owner_id == user.id,
            Collection.name == name
        )
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Collection with this name already exists."
        )

    if tags is None:
        tags = []

    collection = Collection(
        owner_id=user.id,
        name=name,
        tags=tags
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return None


@router.patch("/{collection_id}", status_code=status.HTTP_200_OK)
def update_collection(
        collection_id: uuid.UUID,
        name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        is_default: Optional[bool] = None,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    collection = db.scalar(
        sa.select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found.")

    if name == "DEFAULT":
        raise HTTPException(status_code=400, detail="Cannot rename collection to DEFAULT.")

    if is_default:
        raise HTTPException(status_code=400, detail="Cannot set is_default via update.")

    if name is not None:
        collection.name = name

    if tags is not None:
        collection.tags = tags

    db.commit()
    db.refresh(collection)
    return None


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
        collection_id: uuid.UUID,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    collection = db.scalar(
        sa.select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.owner_id == user.id
        )
    )

    if not collection:
        raise HTTPException(
            status_code=404,
            detail="Collection not found."
        )

    db.delete(collection)
    db.commit()
    return None
