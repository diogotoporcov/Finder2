import os, secrets, uuid, datetime as dt
from typing import Any, Dict
from jose import jwt
from argon2 import PasswordHasher

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALG = os.getenv("JWT_ALG", "HS256")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "30"))

ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        ph.verify(hashed, pw)
        return True
    except Exception:
        return False


def make_jwt(sub: str, scope: str, ttl: dt.timedelta) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: Dict[str, Any] = {
        "iss": "finder2-auth",
        "sub": sub,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def mint_access(user_id: str) -> str:
    return make_jwt(user_id, "access", dt.timedelta(minutes=ACCESS_TTL_MIN))


def mint_refresh(user_id: str) -> str:
    return make_jwt(user_id, "refresh", dt.timedelta(days=REFRESH_TTL_DAYS))
