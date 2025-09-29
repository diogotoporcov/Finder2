import os
import numpy as np
import tritonclient.grpc as grpcclient
from tritonclient.grpc import InferenceServerClient, InferInput, InferRequestedOutput

from finder.services.embedding_service.hashing import sha256_bytes, phash64
from finder.services.embedding_service.preprocess import preprocess_image
from finder.services.singleton_base_service import SingletonBaseService

TRITON_URL = os.getenv("TRITON_URL", "localhost:8001")
MODEL_NAME = os.getenv("TRITON_MODEL", "clip_embedder")
INPUT_NAME = os.getenv("TRITON_INPUT", "INPUT")        # FP32 [N,3,224,224]
OUTPUT_NAME = os.getenv("TRITON_OUTPUT", "EMBEDDING")  # FP32 [N,512]


class EmbeddingService(SingletonBaseService):
    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.client: InferenceServerClient = grpcclient.InferenceServerClient(
            url=TRITON_URL, verbose=False
        )

        self._initialized = True

    def _infer_batch(self, batch_chw_fp32: np.ndarray) -> np.ndarray:
        inp = InferInput(INPUT_NAME, list(batch_chw_fp32.shape), "FP32")
        inp.set_data_from_numpy(batch_chw_fp32)
        out = InferRequestedOutput(OUTPUT_NAME)
        res = self.client.infer(MODEL_NAME, inputs=[inp], outputs=[out])
        embs = res.as_numpy(OUTPUT_NAME)
        norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
        return (embs / norms).astype(np.float32)

    def embed_image(self, img_bytes: bytes) -> dict:
        sha256 = sha256_bytes(img_bytes)
        phash = phash64(img_bytes)

        arr = preprocess_image(img_bytes).astype(np.float32)  # [3,224,224]
        batch = arr[None, ...]                                # [1,3,224,224]

        embs = self._infer_batch(batch)                       # [1,D]
        emb = embs[0]

        return {"sha256": sha256, "phash": phash, "embedding": emb}

    def embed_many(self, images: list[bytes]) -> list[dict]:
        if not images:
            return []

        batch = np.stack([preprocess_image(b) for b in images], axis=0).astype(np.float32)
        embs = self._infer_batch(batch)  # [N,D]
        out = []

        for b, e in zip(images, embs):
            out.append({"sha256": sha256_bytes(b), "phash": phash64(b), "embedding": e})

        return out
