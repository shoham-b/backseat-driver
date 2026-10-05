"""S3-compatible `DatasetStore` (AWS S3, GCS interoperability, any S3 API server) over aioboto3.

Credentials come from boto3's standard chain (`AWS_ACCESS_KEY_ID` and friends), not from `Settings`. aioboto3 is
imported lazily, and a client is opened for each operation (it belongs to the event loop it was created on, and the
sync edges start a loop per call), so constructing the store never connects.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from backseat_driver.read.s3.dataset_store import DatasetStore

_SCHEME = "s3://"
_MISSING = {"404", "NoSuchKey", "NotFound"}


def make_s3_client(endpoint_url: str | None) -> AbstractAsyncContextManager[Any]:
    import aioboto3

    return aioboto3.Session().client("s3", endpoint_url=endpoint_url)


class S3DatasetStore(DatasetStore):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        make_client: Callable[[str | None], AbstractAsyncContextManager[Any]] = make_s3_client,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._make_client = make_client

    def uri_for(self, key: str) -> str:
        return f"{_SCHEME}{self._bucket}/{key}"

    async def exists(self, key: str) -> bool:
        async with self._make_client(self._endpoint_url) as client:
            listing = await client.list_objects_v2(Bucket=self._bucket, Prefix=key, MaxKeys=1)
        return any(entry["Key"] == key for entry in listing.get("Contents", []))

    async def upload(self, key: str, path: Path) -> None:
        async with self._make_client(self._endpoint_url) as client:
            await client.upload_file(str(path), self._bucket, key)

    async def download_prefix(self, prefix: str, directory: Path) -> None:
        async with self._make_client(self._endpoint_url) as client:
            keys = [
                entry["Key"]
                async for page in client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix)
                for entry in page.get("Contents", [])
            ]
            if not keys:
                raise FileNotFoundError(
                    f"No objects under s3://{self._bucket}/{prefix}: has the dataset been uploaded?"
                )
            targets = {key: directory / key.removeprefix(prefix) for key in keys}
            await asyncio.to_thread(_make_parents, targets.values())
            await asyncio.gather(
                *(client.download_file(self._bucket, key, str(target)) for key, target in targets.items())
            )

    @asynccontextmanager
    async def local_copy(self, uri: str) -> AsyncIterator[Path]:
        bucket, key = self._parse(uri)
        # The object's own file name is kept: the Anthropic backend picks the media type from the suffix.
        with TemporaryDirectory(prefix="backseat-driver-") as directory:
            target = Path(directory) / PurePosixPath(key).name
            try:
                async with self._make_client(self._endpoint_url) as client:
                    await client.download_file(bucket, key, str(target))
            except Exception as exc:
                if getattr(exc, "response", {}).get("Error", {}).get("Code") in _MISSING:
                    raise FileNotFoundError(f"No object at {uri}") from exc
                raise
            yield target

    @staticmethod
    def _parse(uri: str) -> tuple[str, str]:
        bucket, _, key = uri.removeprefix(_SCHEME).partition("/")
        if not uri.startswith(_SCHEME) or not bucket or not key:
            raise ValueError(f"Not an S3 image URI: {uri!r}")
        return bucket, key


def _make_parents(targets: Any) -> None:
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
