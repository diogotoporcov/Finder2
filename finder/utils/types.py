from enum import StrEnum

import torch


class DeviceType(StrEnum):
    GPU = "cuda"
    CPU = "cpu"
    AUTO = GPU if torch.cuda.is_available() else CPU
