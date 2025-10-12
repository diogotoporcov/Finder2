from pathlib import Path

import torch
import torch.nn as nn
import clip

from finder.utils.types import DeviceType

path = Path("./models/embedder/1/model.onnx")

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)
model.float()
model.eval()


class ClipModel(nn.Module):
    def __init__(self, clip_model: nn.Module):
        super().__init__()
        self.clip_model = clip_model

    def forward(self, x: torch.Tensor):
        return self.clip_model.encode_image(x)


wrapper = ClipModel(model)

dummy = torch.randn(1, 3, 224, 224, dtype=torch.float32).to(device=device)

torch.onnx.export(
    wrapper,
    (dummy, ),
    path,
    input_names=["INPUT"],
    output_names=["EMBEDDING"],
    dynamic_axes={
        "INPUT": {0: "batch"},
        "EMBEDDING": {0: "batch"},
    },
    opset_version=17
)

print(f"Saved `{wrapper.__class__.__name__}` model to {path.absolute()}")