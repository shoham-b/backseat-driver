"""Port for the nuScenes dataset kept in object storage, the one place every worker reads it from.

A one-time `dataset upload` fills it; after that no worker needs the dataset on a disk of its own, except for the
small metadata tables ingest downloads to find the keyframes.
"""

from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path

from backseat_driver.read.images.image_store import ImageStore


class DatasetStore(ImageStore):
    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def upload(self, key: str, path: Path) -> None:
        """Store the file at `path` under `key`, replacing any object already there."""

    @abstractmethod
    async def upload_all(self, files: Mapping[str, Path], skip_existing: bool) -> int:
        """`upload` for many files at once, keyed by object key; returns how many were sent.

        With `skip_existing`, a key already in the store is left alone and not counted. The first failure stops the
        rest.
        """

    @abstractmethod
    async def download_prefix(self, prefix: str, directory: Path) -> None:
        """Download every object under `prefix` into `directory`, keeping the paths below the prefix."""
