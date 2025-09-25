from enum import StrEnum, auto


class DeviceType(StrEnum):
    AUTO = auto()
    GPU = "cuda"
    CPU = "cpu"
