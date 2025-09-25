from abc import ABC
from typing import ClassVar, Dict, Type, Self


class SingletonBaseService(ABC):
    _instances: ClassVar[Dict[Type[Self], Self]] = {}

    def __new__(cls: Type[Self], *args, **kwargs) -> Self:
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance

        return cls._instances[cls]

    @classmethod
    def get_instance(cls: Type[Self]) -> Self:
        if cls not in cls._instances:
            cls._instances[cls] = cls()

        return cls._instances[cls]
