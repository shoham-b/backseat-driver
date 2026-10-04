"""Keeps a local cache of the nuScenes dataset in step with its download URL.

The dataroot is only a cache: the source of truth is the archive at the URL, so deleting the dataroot is always safe.
After a complete extraction a marker file records which archive (URL, ETag, size) filled the cache. Every run asks the
server for the archive's current identity and re-downloads when the marker is missing or no longer matches, so a
half-filled, hand-edited or outdated cache is replaced rather than trusted. The archive is extracted into a scratch
directory and moved into place only once complete, so an interrupted download never looks valid. A server that cannot
be reached is an error, not a reason to trust the cache.
"""

import io
import json
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from loguru import logger

_MARKER = ".nuscenes-cache.json"


# Called after every read of the archive with (bytes downloaded so far, total bytes if the server sent them).
DownloadProgress = Callable[[int, int | None], None]


class LogEveryTenPercent:
    """The default `DownloadProgress`: one log line each time the download passes another 10%."""

    def __init__(self) -> None:
        self._next_report = 10

    def __call__(self, downloaded: int, total: int | None) -> None:
        if not total:
            return
        percent = downloaded * 100 // total
        while percent >= self._next_report:
            logger.info("nuScenes download {}%", self._next_report)
            self._next_report += 10


class _ProgressReader(io.RawIOBase):
    """Reports download progress on every read of `raw`; buffered, it is the real file object `tarfile` expects."""

    def __init__(self, raw: IO[bytes], total: int | None, on_progress: DownloadProgress) -> None:
        self._raw = raw
        self._total = total
        self._on_progress = on_progress
        self._read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        data = self._raw.read(len(buffer))
        buffer[: len(data)] = data
        self._read += len(data)
        self._on_progress(self._read, self._total)
        return len(data)


def _remote_identity(url: str) -> dict[str, str]:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request) as response:
        headers = response.headers
        # file:// URLs (used in tests) carry no ETag; Last-Modified stands in for it.
        etag = headers.get("ETag") or headers.get("Last-Modified") or ""
        return {"url": url, "etag": etag, "size": headers.get("Content-Length") or ""}


def ensure_nuscenes_dataset(dataroot: str, version: str, url: str, on_progress: DownloadProgress | None = None) -> None:
    """Make ``dataroot`` hold the dataset at ``url``, downloading it when absent, incomplete or out of date.

    Download progress goes to ``on_progress``, or to the log every 10% when none is given.
    """
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
        reader = _ProgressReader(response, int(length) if length else None, on_progress or LogEveryTenPercent())
        with tarfile.open(fileobj=io.BufferedReader(reader), mode="r|gz") as archive:
            archive.extractall(scratch, filter="data")

    if not (scratch / version).is_dir():
        shutil.rmtree(root)
        raise RuntimeError(f"Archive from {url} did not contain a {version!r} directory")
    for entry in scratch.iterdir():
        entry.rename(root / entry.name)
    scratch.rmdir()
    marker.write_text(json.dumps(remote))  # last, so its presence means the extraction finished
