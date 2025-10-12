from typing import List

import numpy as np
import tritonclient.grpc as grpcclient
from PIL import Image
from tritonclient.grpc import InferenceServerClient, InferInput, InferRequestedOutput

from finder.config import config
from finder.services.singleton_base_service import SingletonBaseService
from finder.utils.preprocess import preprocess_many

MODEL_NAME = "embedder"
INPUT_NAME = "INPUT"
OUTPUT_NAME = "EMBEDDING"


class EmbeddingService(SingletonBaseService):
    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.client: InferenceServerClient = grpcclient.InferenceServerClient(
            url=config.TRITON_URL, verbose=False
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

    async def embed(self, images: List[Image.Image]) -> np.ndarray[np.float32]:
        batch = await preprocess_many(images)
        return self._infer_batch(batch)
