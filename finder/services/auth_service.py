import datetime as dt
import os
import uuid

from argon2 import PasswordHasher
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from finder.db.models.user import User
from finder.db.models.refresh_token import RefreshToken
from finder.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALG = os.getenv("JWT_ALG", "HS512")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS"))

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
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

    @classmethod
    def mint_access(cls, user_id: str) -> str:
        return cls._make_jwt(user_id, "access", dt.timedelta(minutes=ACCESS_TTL_MIN))

    @classmethod
    def mint_refresh(cls, user_id: str) -> str:
        return cls._make_jwt(user_id, "refresh", dt.timedelta(days=REFRESH_TTL_DAYS))

    @classmethod
    def register(cls, db: Session, username: str, email: str, password: str) -> None:
        if db.scalar(select(User).where((User.username == username) | (User.email == email))):
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
        db.commit()

    @classmethod
    def login(cls, db: Session, username: str, password: str):
        import hashlib
        import datetime as dt
        from jose import jwt

        user = db.scalar(
            select(User)
            .where(User.username == username)
        )
        if not user or not cls.verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials."
            )

        access = cls.mint_access(str(user.id))
        refresh = cls.mint_refresh(str(user.id))

        payload = jwt.get_unverified_claims(refresh)
        hashed_jti = hashlib.sha256(payload["jti"].encode()).hexdigest()

        db.add(RefreshToken(
            user_id=user.id,
            jti_hash=hashed_jti,
            expires_at=dt.datetime.fromtimestamp(payload["exp"], tz=dt.timezone.utc)
        ))

        db.commit()
        return access, refresh

    @classmethod
    def verify_token(cls, token: str, db: Session) -> User:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

        return user

    @classmethod
    def get_current_user(cls, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
        return cls.verify_token(token, db)
