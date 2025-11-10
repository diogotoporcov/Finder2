import contextlib

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from src.routers import register_routers
from src.services.embedding_service import EmbeddingService


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(EmbeddingService.get_instance)
    yield

app = FastAPI(
    title="Finder v2",
    description="Finder v2 is a highly efficient image management system designed for organizing, "
                "storing, and preventing duplicate images in large databases.",
    version="1.0.0",
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    # docs_url=None,
    # redoc_url=None,
    # openapi_url=None
)
register_routers(app)
