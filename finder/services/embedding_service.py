import asyncio
import datetime
import io
import os
import time
from dataclasses import dataclass
from typing import Optional, Union, Iterable, List

import numpy as np
import torch
from PIL import Image
from torchvision import models
from torchvision.models import (
    MobileNet_V3_Large_Weights, ResNet50_Weights
)

from finder.services.singleton_base_service import SingletonBaseService
from finder.utils.types import DeviceType


def log(m): print(f"[{datetime.datetime.now().isoformat()}] {m}", flush=True)


@dataclass(frozen=True)
class TVServiceConfig:
    model_name: str = "mobilenet_v3_large"  # or "resnet50"
    device: DeviceType = DeviceType.AUTO
    max_concurrent: int = 128
    executor_workers: int = os.cpu_count() or 8
    use_autocast_on_cuda: bool = True
    return_numpy: bool = False


class TorchVisionEmbeddingService(SingletonBaseService):
    def __init__(self, config: Optional[TVServiceConfig] = None) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self.config = config or TVServiceConfig()

        if self.config.device == DeviceType.AUTO:
            device = DeviceType.GPU if torch.cuda.is_available() else DeviceType.CPU

        else:
            device = self.config.device

        self.device = torch.device(device)
        log(f"Using device: {self.device}")

        if self.config.model_name == "mobilenet_v3_large":
            weights = MobileNet_V3_Large_Weights.DEFAULT
            self.model = models.mobilenet_v3_large(weights=weights)
            self.model.classifier = torch.nn.Identity()  # 960-d

        elif self.config.model_name == "resnet50":
            weights = ResNet50_Weights.IMAGENET1K_V2
            self.model = models.resnet50(weights=weights)
            self.model.fc = torch.nn.Identity()  # 2048-d
        else:
            raise ValueError("Unsupported model_name")

        self.preprocess = weights.transforms()
        self.model.eval().to(self.device)
        for p in self.model.parameters():
            p.requires_grad_(False)

        self._sem = asyncio.Semaphore(max(1, self.config.max_concurrent))
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=max(1, self.config.executor_workers))
        log(f"Initialized TV service with {self.config.model_name}")

    async def embed(self, images: Iterable[Union[Image.Image, bytes, bytearray]], batch_size: int = 16):
        t0 = time.perf_counter()
        out, batch = [], []
        for img in images:
            batch.append(self._ensure_pil(img))
            if len(batch) == batch_size:
                t1 = time.perf_counter()
                async with self._sem:
                    loop = asyncio.get_running_loop()
                    out.extend(await loop.run_in_executor(self._executor, self._embed_batch_sync, list(batch)))
                log(f"Processed batch of {len(batch)} in {time.perf_counter() - t1:.3f}s")
                batch.clear()
        if batch:
            t1 = time.perf_counter()
            async with self._sem:
                loop = asyncio.get_running_loop()
                out.extend(await loop.run_in_executor(self._executor, self._embed_batch_sync, list(batch)))
            log(f"Processed final batch of {len(batch)} in {time.perf_counter() - t1:.3f}s")

        log(f"Total embed() took {time.perf_counter() - t0:.3f}s")
        return out

    def _embed_batch_sync(self, pils: List[Image.Image]):
        t0 = time.perf_counter()
        tensors = torch.stack([self.preprocess(p) for p in pils], dim=0)
        if self.device.type == DeviceType.GPU:
            tensors = tensors.pin_memory().to(self.device, non_blocking=True)
        else:
            tensors = tensors.to(self.device)

        with torch.inference_mode():
            if self.device.type == DeviceType.GPU and self.config.use_autocast_on_cuda:
                with torch.autocast(device_type=DeviceType.GPU, dtype=torch.float16):
                    feats = self.model(tensors)
            else:
                feats = self.model(tensors)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
        arr = feats.detach().to("cpu").float()
        log(f"_embed_batch_sync on {len(pils)} images took {time.perf_counter() - t0:.3f}s")
        return [np.asarray(v) if self.config.return_numpy else v.numpy().tolist() for v in arr]

    @staticmethod
    def _ensure_pil(x):
        if isinstance(x, (bytes, bytearray)):
            x = Image.open(io.BytesIO(x))
        return x.convert("RGB")

    def warmup(self):
        dummy = Image.new("RGB", (224, 224), color="black")
        self._embed_batch_sync([dummy])
