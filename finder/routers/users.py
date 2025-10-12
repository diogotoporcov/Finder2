from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import event, Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper

from finder.db.models.collection import Collection
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None


@router.patch("/{user_id}")
async def update_user(
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    if user_update.username:
        user.username = user_update.username

    if user_update.email:
        user.email = user_update.email

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
):
    await db.delete(user)
    await db.commit()


@event.listens_for(User, "after_insert")
def create_default_collection(_mapper: Mapper, connection: Connection, target: User):
    connection.execute(
        sa.insert(Collection).values(
            owner_id=target.id,
            name="DEFAULT",
            is_default=True,
        )
    )
