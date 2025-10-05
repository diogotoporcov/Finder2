import os
from dataclasses import dataclass
from typing import List

import numpy as np
import tritonclient.grpc as grpcclient
from tritonclient.grpc import InferenceServerClient, InferInput, InferRequestedOutput

from finder.services.singleton_base_service import SingletonBaseService
from finder.utils.files import load_images_from_bytes
from finder.utils.hashing import generate_phash_many, generate_sha256_many
from finder.utils.preprocess import preprocess_many

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = os.getenv("TRITON_MODEL", "embedder")
INPUT_NAME = os.getenv("TRITON_INPUT", "INPUT")  # FP32 [N,3,224,224]
OUTPUT_NAME = os.getenv("TRITON_OUTPUT", "EMBEDDING")  # FP32 [N,512]


@dataclass
class EmbeddingResult:
    sha256: str
    phash: bytes
    embedding: np.ndarray[np.float32]


class EmbeddingService(SingletonBaseService):
    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.client: InferenceServerClient = grpcclient.InferenceServerClient(
            url=TRITON_URL, verbose=False
        )

        self._initialized = True

    def is_running(self) -> bool:
        try:
            return (
                    self.client.is_server_live()
                    and self.client.is_server_ready()
                    and self.client.is_model_ready(MODEL_NAME)
            )

        except Exception:
            return False

    def _infer_batch(self, batch_chw_fp32: np.ndarray[np.float32]) -> np.ndarray[np.float32]:
        inp = InferInput(INPUT_NAME, list(batch_chw_fp32.shape), "FP32")
        inp.set_data_from_numpy(batch_chw_fp32)
        out = InferRequestedOutput(OUTPUT_NAME)
        res = self.client.infer(MODEL_NAME, inputs=[inp], outputs=[out])
        embs = res.as_numpy(OUTPUT_NAME)
        norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
        return (embs / norms).astype(np.float32)

    async def embed(self, images_bytes_list: List[bytes]) -> List[EmbeddingResult]:
        if not images_bytes_list:
            return []

        images = await load_images_from_bytes(images_bytes_list)

        sha256_list = await generate_sha256_many(images_bytes_list)
        phash_list = await generate_phash_many(images, hash_size=8)

        batch = await preprocess_many(images)

        embeddings = self._infer_batch(batch)  # [N,D]

        return [
            EmbeddingResult(
                sha256=sha,
                phash=ph,
                embedding=emb
            )
            for sha, ph, emb in zip(sha256_list, phash_list, embeddings)
        ]
