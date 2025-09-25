import time
from contextlib import asynccontextmanager
from typing import List, Dict

from fastapi import FastAPI, UploadFile, File
from starlette import status
from starlette.responses import JSONResponse

from finder.services.embedding_service import TorchVisionEmbeddingService, log


@asynccontextmanager
async def lifespan(_app: FastAPI):
    TorchVisionEmbeddingService.get_instance().warmup()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/embed")
async def embed_images(files: List[UploadFile] = File(...)) -> JSONResponse:
    t0 = time.perf_counter()
    log("API request start")

    service = TorchVisionEmbeddingService.get_instance()

    t1 = time.perf_counter()
    file_contents = [await file.read() for file in files]
    file_names = [file.filename for file in files]
    log(f"Read {len(files)} files in {time.perf_counter() - t1:.3f}s")

    t2 = time.perf_counter()
    results = await service.embed(file_contents)
    log(f"Embedding took {time.perf_counter() - t2:.3f}s")

    embeddings: Dict[str, List[float]] = {
        name: embedding[:3] for name, embedding in zip(file_names, results)
    }

    resp = JSONResponse(status_code=status.HTTP_200_OK, content={"embeddings": embeddings})
    log(f"API request end in {time.perf_counter() - t0:.3f}s")
    return resp
