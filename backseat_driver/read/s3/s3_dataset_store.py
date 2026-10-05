"""S3-compatible `DatasetStore` (AWS S3, GCS interoperability, any S3 API server) over boto3.

Credentials come from boto3's standard chain (`AWS_ACCESS_KEY_ID` and friends), not from `Settings`. boto3 is
imported lazily and the client is built on first use, so constructing the store never connects.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from backseat_driver.read.s3.dataset_store import DatasetStore

_SCHEME = "s3://"
_MISSING = {"404", "NoSuchKey", "NotFound"}


def make_s3_client(endpoint_url: str | None) -> Any:
    import boto3

    return boto3.client("s3", endpoint_url=endpoint_url)


class S3DatasetStore(DatasetStore):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        make_client: Callable[[str | None], Any] = make_s3_client,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._make_client = make_client
        self._client: Any = None

    def uri_for(self, key: str) -> str:
        return f"{_SCHEME}{self._bucket}/{key}"

    def exists(self, key: str) -> bool:
        listing = self._get_client().list_objects_v2(Bucket=self._bucket, Prefix=key, MaxKeys=1)
        return any(entry["Key"] == key for entry in listing.get("Contents", []))

    def upload(self, key: str, path: Path) -> None:
        self._get_client().upload_file(str(path), self._bucket, key)

    def download_prefix(self, prefix: str, directory: Path) -> None:
        client = self._get_client()
        found = False
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix):
            for entry in page.get("Contents", []):
                target = directory / entry["Key"].removeprefix(prefix)
                target.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(self._bucket, entry["Key"], str(target))
                found = True
        if not found:
            raise FileNotFoundError(f"No objects under s3://{self._bucket}/{prefix}: has the dataset been uploaded?")

    @asynccontextmanager
    async def local_copy(self, uri: str) -> AsyncIterator[Path]:
        bucket, key = self._parse(uri)
        # The object's own file name is kept: the Anthropic backend picks the media type from the suffix.
        with TemporaryDirectory(prefix="backseat-driver-") as directory:
            target = Path(directory) / PurePosixPath(key).name
            try:
                # boto3 blocks, so the download runs on a worker thread.
                await asyncio.to_thread(self._get_client().download_file, bucket, key, str(target))
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

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._make_client(self._endpoint_url)
        return self._client
