import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, Union, Iterable, List

import numpy as np
import torch
from PIL import Image

import clip

from finder.utils.types import DeviceType


@dataclass(frozen=True)
class CLIPServiceConfig:
    model_name: str = "ViT-B/32"          # 512-dim
    device: Optional[DeviceType] = None   # "cuda", "cpu", or None to auto
    download_root: Optional[str] = None   # cache dir (e.g., settings.MODEL_CACHE_DIR)
    max_concurrent: int = 2               # cap concurrent inferences
    executor_workers: int = 2             # threads to offload sync work
    use_autocast_on_cuda: bool = True     # mixed precision on GPU
    return_numpy: bool = False            # set True if you prefer np.ndarray


class CLIPEmbeddingService:
    """
    Fast, concurrency-safe CLIP image embedding service.

    - Accepts PIL.Image.Image or image bytes
    - Returns L2-normalized embedding as List[float] (or np.ndarray if configured)
    - Safe under load via a semaphore + thread executor
    - GPU-aware: autocast + non_blocking transfers on CUDA
    """

    def __init__(self, config: Optional[CLIPServiceConfig] = None) -> None:
        self.config = config or CLIPServiceConfig()

        if not self.config.device:
            device_name = DeviceType.GPU if torch.cuda.is_available() else DeviceType.CPU

        else:
            device_name = self.config.device

        self.device = torch.device(device_name)

        self.model, self.preprocess = clip.load(
            self.config.model_name,
            device=self.device,
            jit=False,
            download_root=self.config.download_root,
        )
        self.model.eval()
        for param in self.model.parameters():
            param.requires_grad_(False)

        # Concurrency controls
        self._sem = asyncio.Semaphore(max(1, self.config.max_concurrent))
        self._executor = ThreadPoolExecutor(max_workers=max(1, self.config.executor_workers))

    def tensor_to_device(self, tensor: torch.Tensor) -> torch.Tensor:
        if self.device.type == DeviceType.CPU:
            return tensor.to(self.device)
        return tensor.pin_memory().to(self.device, non_blocking=True)

    # ------------- Public API -------------

    async def embed_single(
        self,
        image: Union[Image.Image, bytes, bytearray],
    ) -> Union[List[float], np.ndarray]:
        """
        Async embedding for a single image (PIL or raw bytes).
        Returns a 512-dim L2-normalized embedding.
        """
        pil = self._ensure_pil(image)
        async with self._sem:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._embed_sync, pil)

    async def embed_many(
            self,
            images: Iterable[Union[Image.Image, bytes, bytearray]],
            batch_size: int = 16,
    ) -> List[Union[List[float], np.ndarray]]:
        """
        Async embedding for multiple images with simple batching.
        Converts bytes→PIL here; batches processed sequentially.
        """
        results: List[Union[List[float], np.ndarray]] = []
        batch: list[Image.Image] = []
        for img in images:
            batch.append(self._ensure_pil(img))
            if len(batch) == batch_size:
                async with self._sem:
                    loop = asyncio.get_running_loop()
                    results.extend(await loop.run_in_executor(
                        self._executor, self._embed_batch_sync, list(batch)
                    ))
                batch.clear()

        if batch:
            async with self._sem:
                loop = asyncio.get_running_loop()
                results.extend(await loop.run_in_executor(
                    self._executor, self._embed_batch_sync, list(batch)
                ))

        return results

    def warmup(self) -> None:
        size = 224, 224
        arr = np.random.randint(0, 256, (*size, 3), dtype=np.uint8)
        img = Image.fromarray(arr, "RGB")
        _ = self._embed_sync(img)

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    # ------------- Internal (sync) -------------

    def _embed_sync(self, pil: Image.Image) -> Union[List[float], np.ndarray]:
        """Sync embedding for a single PIL image only."""
        tensor = self.preprocess(pil).unsqueeze(0)
        tensor = self.tensor_to_device(tensor)

        with torch.inference_mode():
            if self.device.type == DeviceType.GPU and self.config.use_autocast_on_cuda:
                with torch.autocast(device_type=DeviceType.GPU, dtype=torch.float16):
                    feats = self.model.encode_image(tensor)
            else:
                feats = self.model.encode_image(tensor)

        feats = feats[0]
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)

        out = feats.detach().to(DeviceType.CPU).float()
        if self.config.return_numpy:
            return np.asarray(out)

        return out.numpy().tolist()

    def _embed_batch_sync(self, pils: List[Image.Image]):
        """Sync embedding for a batch of PIL images."""
        tensors = torch.stack([self.preprocess(p) for p in pils], dim=0)
        tensors = self.tensor_to_device(tensors)

        with torch.inference_mode():
            if self.device.type == DeviceType.GPU and self.config.use_autocast_on_cuda:
                with torch.autocast(device_type=DeviceType.GPU, dtype=torch.float16):
                    feats = self.model.encode_image(tensors)
            else:
                feats = self.model.encode_image(tensors)

        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        out = feats.detach().to(DeviceType.CPU).float()

        if self.config.return_numpy:
            return [np.asarray(vec) for vec in out]

        return [vec.numpy().tolist() for vec in out]

    # ------------- Utils -------------

    @staticmethod
    def _ensure_pil(image: Union[Image.Image, bytes, bytearray]) -> Image.Image:
        if isinstance(image, (bytes, bytearray)):
            image = Image.open(io.BytesIO(image))

        return image.convert("RGB")
