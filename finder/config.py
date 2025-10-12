from pathlib import Path

import humanfriendly
from pydantic import BaseModel, AnyUrl
from typing import List
from dotenv import load_dotenv
import os

load_dotenv()


class Config(BaseModel):
    # Images
    DB_IMAGE: str
    TRITON_IMAGE: str
    FINDER_IMAGE: str

    # Database
    DB_HOST: str
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    PGDATA: str
    POSTGRES_PORT: int
    DATABASE_URL: str

    # JWT & Security
    JWT_SECRET: str
    JWT_ALG: str
    ACCESS_TTL_MIN: int
    REFRESH_TTL_DAYS: int

    # Uploads
    ALLOWED_MIME_TYPES: List[str]
    MAX_FILE_SIZE: int
    MAX_UPLOAD_FILES: int
    STORAGE_PATH: Path

    # Triton
    TRITON_HOST: str
    TRITON_HTTP_PORT: int
    TRITON_GRPC_PORT: int
    TRITON_METRICS_PORT: int
    TRITON_URL: str

    # FastAPI
    FASTAPI_HOST: str
    FASTAPI_PORT: int

    # Async I/O
    MAX_CONCURRENT_IO: int


config = Config(
    DB_IMAGE=os.environ["DB_IMAGE"],
    TRITON_IMAGE=os.environ["TRITON_IMAGE"],
    FINDER_IMAGE=os.environ["FINDER_IMAGE"],

    DB_HOST=os.environ["DB_HOST"],
    POSTGRES_DB=os.environ["POSTGRES_DB"],
    POSTGRES_USER=os.environ["POSTGRES_USER"],
    POSTGRES_PASSWORD=os.environ["POSTGRES_PASSWORD"],
    PGDATA=os.environ["PGDATA"],
    POSTGRES_PORT=int(os.environ["POSTGRES_PORT"]),
    DATABASE_URL=str(AnyUrl(os.environ["DATABASE_URL"])),

    JWT_SECRET=os.environ["JWT_SECRET"],
    JWT_ALG=os.environ["JWT_ALG"],
    ACCESS_TTL_MIN=int(os.environ["ACCESS_TTL_MIN"]),
    REFRESH_TTL_DAYS=int(os.environ["REFRESH_TTL_DAYS"]),

    ALLOWED_MIME_TYPES=os.environ["ALLOWED_MIME_TYPES"].split(","),
    MAX_FILE_SIZE=humanfriendly.parse_size(os.environ["MAX_FILE_SIZE"]),
    MAX_UPLOAD_FILES=int(os.environ["MAX_UPLOAD_FILES"]),
    STORAGE_PATH=Path(os.environ["STORAGE_PATH"]),

    TRITON_HOST=os.environ["TRITON_HOST"],
    TRITON_HTTP_PORT=int(os.environ["TRITON_HTTP_PORT"]),
    TRITON_GRPC_PORT=int(os.environ["TRITON_GRPC_PORT"]),
    TRITON_METRICS_PORT=int(os.environ["TRITON_METRICS_PORT"]),
    TRITON_URL=os.environ["TRITON_URL"],

    FASTAPI_HOST=os.environ["FASTAPI_HOST"],
    FASTAPI_PORT=int(os.environ["FASTAPI_PORT"]),

    MAX_CONCURRENT_IO=int(os.environ["MAX_CONCURRENT_IO"]),
)

__all__ = ["config"]
