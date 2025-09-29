from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from finder.services.embedding_service.embedder import EmbeddingService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedder = await run_in_threadpool(EmbeddingService.get_instance)
    yield


app = FastAPI(lifespan=lifespan)
