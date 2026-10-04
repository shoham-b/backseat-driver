"""Port for the nuScenes dataset kept in object storage, the one place every worker reads it from.

A one-time `dataset upload` fills it; after that no worker needs the dataset on a disk of its own, except for the
small metadata tables ingest downloads to find the keyframes.
"""

from abc import abstractmethod
from pathlib import Path

from backseat_driver.read.image_store import ImageStore


class DatasetStore(ImageStore):
    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def upload(self, key: str, path: Path) -> None:
        """Store the file at `path` under `key`, replacing any object already there."""

    @abstractmethod
    def download_prefix(self, prefix: str, directory: Path) -> None:
        """Download every object under `prefix` into `directory`, keeping the paths below the prefix."""
