"""The business logic for serving keyframe images to clients.

The API (and anything else that hands out images) goes through this, never to the store: it decides which keys may be
read and turns a missing object into the domain's `NotFoundError`, so the store's own errors (a missing file, a missing
S3 object) never reach the HTTP layer.
"""

import anyio

from backseat_driver.errors import NotFoundError
from backseat_driver.read.images.image_keys import validate_image_key
from backseat_driver.read.images.image_store import ImageStore


class ImageService:
    def __init__(self, store: ImageStore) -> None:
        self._store = store

    async def read(self, key: str) -> bytes:
        """The image's bytes. Raises `UnprocessableError` for a key that is not a keyframe image, `NotFoundError` for
        one that names nothing."""
        validate_image_key(key)
        try:
            async with self._store.local_copy(self._store.uri_for(key)) as path:
                return await anyio.Path(path).read_bytes()
        except FileNotFoundError as exc:
            raise NotFoundError(f"image {key!r} not found") from exc
