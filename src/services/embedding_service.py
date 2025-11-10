from typing import List
import time
import numpy as np
import tritonclient.grpc as grpcclient
from PIL import Image
from tritonclient.grpc import InferenceServerClient, InferInput, InferRequestedOutput

from src.config import config
from src.services.singleton_base_service import SingletonBaseService
from src.utils.preprocess import preprocess_many

MODEL_NAME = "embedder"
INPUT_NAME = "INPUT"
OUTPUT_NAME = "EMBEDDING"


class EmbeddingService(SingletonBaseService):
    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self._connect()

    def _connect(self):
        """Initialize or reinitialize Triton client connection."""
        self.client: InferenceServerClient = grpcclient.InferenceServerClient(
            url=config.TRITON_URL, verbose=False
        )

    def _check_connection(self) -> bool:
        """Check if server and model are ready."""
        try:
            return (
                self.client.is_server_live()
                and self.client.is_server_ready()
                and self.client.is_model_ready(MODEL_NAME)
            )

        except Exception:
            return False

    def is_running(self) -> bool:
        """Detect server availability and reconnect if needed."""
        if not self._check_connection():
            try:
                self._connect()
                return self._check_connection()

            except Exception:
                return False

        return True

    def wait_until_ready(
            self,
            timeout: int = config.TRITON_WAIT_TIMEOUT,
            interval: float = config.TRITON_WAIT_INTERVAL
    ) -> bool:
        """
        Wait until the Triton server and model are ready.
        Returns True if ready within timeout, else False.
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.is_running():
                return True

            time.sleep(interval)

        return False

    def _infer_batch(self, batch_chw_fp32: np.ndarray[np.float32]) -> np.ndarray[np.float32]:
        """Run inference on a preprocessed batch and normalize embeddings."""
        inp = InferInput(INPUT_NAME, list(batch_chw_fp32.shape), "FP32")
        inp.set_data_from_numpy(batch_chw_fp32)
        out = InferRequestedOutput(OUTPUT_NAME)
        res = self.client.infer(MODEL_NAME, inputs=[inp], outputs=[out])
        embs = res.as_numpy(OUTPUT_NAME)
        norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
        return (embs / norms).astype(np.float32)

    async def embed(self, images: List[Image.Image]) -> np.ndarray[np.float32]:
        """Preprocess images and run embedding inference."""
        if not self.is_running():
            raise ConnectionError("Triton server is not available.")
        batch = await preprocess_many(images)
        return self._infer_batch(batch)
