from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.user import User
from src.db.session import get_db
from src.services.auth_service import AuthService

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


class UserUpdate(BaseModel):
    """Payload to update user details."""

    username: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=32,
        description="New username.",
        examples=["diogo"],
    )

    email: Optional[EmailStr] = Field(
        default=None,
        description="New email address.",
        examples=["diogotoporcov@gmail.com"],
    )


class UserOut(BaseModel):
    """User details."""

    id: str = Field(
        ...,
        description="User ID.",
    )

    username: str = Field(
        ...,
        description="Username.",
    )

    email: EmailStr = Field(
        ...,
        description="Email address.",
    )

    model_config = ConfigDict(
        from_attributes=True
    )


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Update user",
    description="Update username or email of the authenticated user.",
    responses={
        200: {"description": "User updated."},
        400: {"description": "Invalid data."},
        401: {"description": "Unauthorized."},
    },
)
async def update_user(
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> UserOut:
    """
    Update the authenticated user's details.
    """

    if user_update.username:
        user.username = user_update.username

    if user_update.email:
        user.email = user_update.email

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete the authenticated user account.",
    responses={
        204: {"description": "User deleted."},
        401: {"description": "Unauthorized."},
    },
)
async def delete_user(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(AuthService.get_current_user),
) -> None:
    """
    Delete the authenticated user.
    """

    await db.delete(user)
    await db.commit()
