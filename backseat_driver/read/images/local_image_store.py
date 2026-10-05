"""`ImageStore` for a single machine: keys are paths below the dataroot, so nothing is copied."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from backseat_driver.read.images.image_store import ImageStore


class LocalImageStore(ImageStore):
    """Used by the monolith, whose ingest and caption handlers share the process and its filesystem."""

    def __init__(self, dataroot: str) -> None:
        self._root = Path(dataroot).resolve()

    def uri_for(self, key: str) -> str:
        path = (self._root / key).resolve()
        # Keys also come from the image endpoint, so one that climbs out of the dataroot must not resolve.
        if not path.is_relative_to(self._root):
            raise ValueError(f"Image key {key!r} is outside the dataroot")
        return str(path)

    @asynccontextmanager
    async def local_copy(self, uri: str) -> AsyncIterator[Path]:
        # The file is the dataset's own, so it is yielded in place and never deleted on exit.
        yield Path(uri)
