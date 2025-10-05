import contextlib

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from finder.routers import register_routers
from finder.services.embedding_service import EmbeddingService


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(EmbeddingService.get_instance)
    yield


app = FastAPI(lifespan=lifespan)
register_routers(app)
