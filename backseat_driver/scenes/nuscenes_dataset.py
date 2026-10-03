"""Keeps a local cache of the nuScenes dataset in step with its download URL.

The dataroot is only a cache: the source of truth is the archive at the URL, so deleting the dataroot is always safe.
After a complete extraction a marker file records which archive (URL, ETag, size) filled the cache. Every run asks the
server for the archive's current identity and re-downloads when the marker is missing or no longer matches, so a
half-filled, hand-edited or outdated cache is replaced rather than trusted. The archive is extracted into a scratch
directory and moved into place only once complete, so an interrupted download never looks valid. A server that cannot
be reached is an error, not a reason to trust the cache.
"""

import json
import shutil
import tarfile
import urllib.request
from pathlib import Path
from typing import IO

from loguru import logger

from backseat_driver.scenes.dataset_cache import DatasetCache

_MARKER = ".nuscenes-cache.json"


class _ProgressReader:
    """File-like wrapper that logs download progress every 10%."""

    def __init__(self, raw: IO[bytes], total: int | None) -> None:
        self._raw = raw
        self._total = total
        self._read = 0
        self._next_report = 10

    def read(self, size: int = -1) -> bytes:
        data = self._raw.read(size)
        self._read += len(data)
        if self._total:
            percent = self._read * 100 // self._total
            while percent >= self._next_report:
                logger.info("nuScenes download {}%", self._next_report)
                self._next_report += 10
        return data


def _remote_identity(url: str) -> dict[str, str]:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request) as response:
        headers = response.headers
        # file:// URLs (used in tests) carry no ETag; Last-Modified stands in for it.
        etag = headers.get("ETag") or headers.get("Last-Modified") or ""
        return {"url": url, "etag": etag, "size": headers.get("Content-Length") or ""}


def ensure_nuscenes_dataset(dataroot: str, version: str, url: str) -> None:
    """Make ``dataroot`` hold the dataset at ``url``, downloading it when absent, incomplete or out of date."""
    root = Path(dataroot)
    marker = root / _MARKER
    remote = _remote_identity(url)
    if marker.is_file() and (root / version).is_dir() and json.loads(marker.read_text()) == remote:
        return

    logger.info("nuScenes cache in {} is missing or out of date; downloading {}", root, url)
    shutil.rmtree(root, ignore_errors=True)
    scratch = root / ".download"
    scratch.mkdir(parents=True)
    with urllib.request.urlopen(url) as response:
        length = response.headers.get("Content-Length")
        reader = _ProgressReader(response, int(length) if length else None)
        # Stream mode only ever calls read(); the stubs demand a seekable, writable file object regardless.
        with tarfile.open(fileobj=reader, mode="r|gz") as archive:  # type: ignore
            archive.extractall(scratch, filter="data")

    if not (scratch / version).is_dir():
        shutil.rmtree(root)
        raise RuntimeError(f"Archive from {url} did not contain a {version!r} directory")
    for entry in scratch.iterdir():
        entry.rename(root / entry.name)
    scratch.rmdir()
    marker.write_text(json.dumps(remote))  # last, so its presence means the extraction finished


class NuScenesDatasetCache(DatasetCache):
    def __init__(self, url: str) -> None:
        self._url = url

    def ensure(self, dataroot: str, version: str) -> None:
        ensure_nuscenes_dataset(dataroot, version, self._url)
