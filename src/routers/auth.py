from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.config import config
from src.db.session import get_db
from src.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


class RegisterIn(BaseModel):
    """Payload to create a new user account."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="Unique username.",
        examples=["diogo"],
    )

    email: EmailStr = Field(
        ...,
        description="Valid and unique email address.",
        examples=["diogotoporcov@gmail.com"],
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=64,
        description="User password.",
        examples=["3w6mYtzE?D$d"],
    )


class LoginIn(BaseModel):
    """Credentials used to obtain access and refresh tokens."""

    username: str = Field(
        ...,
        description="Username chosen during registration.",
        examples=["diogo"],
    )

    password: str = Field(
        ...,
        max_length=64,
        description="Plain-text password chosen during registration.",
        examples=["3w6mYtzE?D$d"],
    )


class RefreshIn(BaseModel):
    """Payload to rotate an existing (valid) refresh token."""
    refresh_token: str = Field(
        ...,
        description="Previously issued refresh token in JWT format.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class TokenOut(BaseModel):
    """OAuth2-compatible bearer token response."""

    token_type: str = Field(
        "bearer",
        description="Token type. Always 'bearer'.",
        examples=["bearer"],
    )

    access_token: str = Field(
        ...,
        description="Short-lived JWT used to authorize API requests.",
    )

    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds.",
        examples=[config.ACCESS_TTL_MIN * 60],
    )

    refresh_token: str = Field(
        ...,
        description="Long-lived JWT used to obtain new access tokens.",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description=(
            "Create a new user account. "
            "On success, no body is returned."
    ),
    responses={
        status.HTTP_201_CREATED: {
            "description": "User registered successfully.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid payload or weak password policy violation.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Username or email already in use.",
        },
    },
)
async def register(
        credentials: RegisterIn,
        db: AsyncSession = Depends(get_db)
) -> None:
    """
    Register a new user.

    `username` and `email` must be unique.
    """

    await AuthService.register(db, credentials.username, str(credentials.email), credentials.password)


@router.post(
    "/login",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain tokens",
    description=(
        "Authenticate with username and password. "
        "Returns a short-lived access token and a long-lived refresh token."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Authentication successful. Tokens returned.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request body.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Invalid username or password.",
        },
    },
)
async def login(
        credentials: LoginIn,
        db: AsyncSession = Depends(get_db)
) -> TokenOut:
    """
    Login with `username` and `password`.

    Returns:
    - `access_token`: use in the `Authorization: Bearer <token>` header.
    - `refresh_token`: use with `/auth/refresh` when the access token expires.
    """

    access, refresh = await AuthService.login(db, credentials.username, credentials.password)
    return TokenOut(
        token_type="bearer",
        access_token=access,
        refresh_token=refresh,
        expires_in=config.ACCESS_TTL_MIN * 60
    )


@router.post(
    "/refresh",
    response_model=TokenOut,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description=(
        "Exchange a valid refresh token for a new access token. "
        "If the refresh token is invalid, expired, or revoked, an error is returned."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "New access token issued.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request body.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Invalid, expired, or revoked refresh token.",
        },
    },
)
async def refresh(
        body: RefreshIn,
        db: AsyncSession = Depends(get_db)
) -> TokenOut:
    data = await AuthService.refresh(db, body.refresh_token)
    return TokenOut(
        token_type="bearer",
        access_token=data["access_token"],
        refresh_token=body.refresh_token,
        expires_in=data["expires_in"]
    )
