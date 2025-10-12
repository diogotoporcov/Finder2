from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from finder.config import config
from finder.db.session import get_db
from finder.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    token_type: str = "bearer"
    access_token: str
    expires_in: int
    refresh_token: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(credentials: RegisterIn, db: AsyncSession = Depends(get_db)):
    await AuthService.register(db, credentials.username, str(credentials.email), credentials.password)


@router.post("/login", response_model=TokenOut, status_code=status.HTTP_200_OK)
async def login(credentials: LoginIn, db: AsyncSession = Depends(get_db)):
    access, refresh = await AuthService.login(db, credentials.username, credentials.password)
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=config.ACCESS_TTL_MIN * 60)


@router.post("/refresh", response_model=TokenOut, status_code=status.HTTP_200_OK)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    data = await AuthService.refresh(db, body.refresh_token)
    return TokenOut(
        access_token=data["access_token"],
        refresh_token=body.refresh_token,
        expires_in=data["expires_in"]
    )
