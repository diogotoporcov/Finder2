from enum import StrEnum


class DeviceType(StrEnum):
    GPU = "cuda"
    CPU = "cpu"
