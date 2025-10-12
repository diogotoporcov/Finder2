from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from starlette import status

from finder.db.session import get_db
from finder.services.auth_service import AuthService, ACCESS_TTL_MIN

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token_type: str = "bearer"
    access_token: str
    expires_in: int
    refresh_token: str


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(credentials: RegisterIn, db: Session = Depends(get_db)):
    AuthService.register(db, credentials.username, str(credentials.email), credentials.password)


@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
)
def login(credentials: LoginIn, db: Session = Depends(get_db)):
    access, refresh = AuthService.login(db, credentials.username, credentials.password)
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=ACCESS_TTL_MIN * 60)
