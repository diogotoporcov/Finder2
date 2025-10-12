import datetime as dt
import hashlib
import uuid

# noinspection PyPackageRequirements
from argon2 import PasswordHasher
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finder.config import config
from finder.db.models.refresh_token import RefreshToken
from finder.db.models.user import User
from finder.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
ph = PasswordHasher()


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        return ph.hash(password)

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            return ph.verify(hashed, password)
        except Exception:
            return False

    @staticmethod
    def _make_jwt(sub: str, scope: str, ttl: dt.timedelta) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        payload = {
            "iss": "finder2-auth",
            "sub": sub,
            "scope": scope,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)

    @classmethod
    def mint_access(cls, user_id: str) -> str:
        return cls._make_jwt(user_id, "access", dt.timedelta(minutes=config.ACCESS_TTL_MIN))

    @classmethod
    def mint_refresh(cls, user_id: str) -> str:
        return cls._make_jwt(user_id, "refresh", dt.timedelta(days=config.REFRESH_TTL_DAYS))

    @classmethod
    async def register(cls, db: AsyncSession, username: str, email: str, password: str) -> None:
        existing = await db.scalar(
            select(User).where((User.username == username) | (User.email == email))
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email is already in use."
            )

        user = User(
            username=username,
            email=email,
            hashed_password=cls.hash_password(password)
        )

        db.add(user)
        await db.commit()

    @classmethod
    async def login(cls, db: AsyncSession, username: str, password: str):
        user = await db.scalar(select(User).where(User.username == username))
        if not user or not cls.verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials."
            )

        access = cls.mint_access(str(user.id))
        refresh = cls.mint_refresh(str(user.id))

        payload = jwt.get_unverified_claims(refresh)
        hashed_jti = hashlib.sha256(payload["jti"].encode()).hexdigest()

        db.add(
            RefreshToken(
                user_id=user.id,
                jti_hash=hashed_jti,
                expires_at=dt.datetime.fromtimestamp(payload["exp"], tz=dt.timezone.utc)
            )
        )
        await db.commit()
        return access, refresh

    @classmethod
    async def verify_token(cls, token: str, db: AsyncSession) -> User:
        try:
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

        user = await db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

        return user

    @classmethod
    async def get_current_user(
        cls,
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        return await cls.verify_token(token, db)

    @classmethod
    async def refresh(cls, db: AsyncSession, refresh_token: str):
        try:
            payload = jwt.decode(refresh_token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
            if payload.get("scope") != "refresh":
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token scope.")
        except JWTError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing subject claim.")

        hashed_jti = hashlib.sha256(payload["jti"].encode()).hexdigest()

        db_token = await db.scalar(
            select(RefreshToken).where(
                RefreshToken.jti_hash == hashed_jti,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > dt.datetime.now(dt.timezone.utc)
            )
        )
        if not db_token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired.")

        new_access = cls.mint_access(user_id)
        return {"access_token": new_access, "token_type": "bearer", "expires_in": config.ACCESS_TTL_MIN * 60}
