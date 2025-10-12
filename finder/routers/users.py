from typing import Optional

from fastapi import APIRouter, Depends, status
import sqlalchemy as sa
from sqlalchemy import event, Connection
from sqlalchemy.orm import Session, Mapper

from finder.db.models.collection import Collection
from finder.db.models.user import User
from finder.db.session import get_db
from finder.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/{user_id}")
def update_user(
        username: Optional[str] = None,
        email: Optional[str] = None,
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    if username:
        user.username = username

    if email:
        user.email = email

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
        db: Session = Depends(get_db),
        user: User = Depends(AuthService.get_current_user)
):
    db.delete(user)
    db.commit()
    return None


@event.listens_for(User, "after_insert")
def create_default_collection(_mapper: Mapper, connection: Connection, target: "User"):
    connection.execute(
        sa.insert(Collection).values(
            owner_id=target.id,
            name="DEFAULT",
            is_default=True,
        )
    )