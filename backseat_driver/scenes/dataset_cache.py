"""Port for making a dataset available on local disk. The nuScenes cache lives next to it."""

from abc import ABC, abstractmethod


class DatasetCache(ABC):
    """Anything that can make sure ``dataroot`` holds a usable copy of a dataset version."""

    @abstractmethod
    def ensure(self, dataroot: str, version: str) -> None: ...
