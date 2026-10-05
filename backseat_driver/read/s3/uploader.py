"""Copies a local nuScenes dataset into the `DatasetStore`: the one step that needs the dataset on a disk."""

import asyncio
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from backseat_driver.read.s3.dataset_store import DatasetStore


@dataclass(frozen=True)
class UploadResult:
    uploaded: int
    skipped: int


class DatasetUploader:
    """Uploads `<version>/*` (the metadata tables) and `samples/<camera>/*` (the keyframe candidates).

    Sweeps and maps are never read by the workers, so they stay behind. Keys are dataset-relative paths. The tables are
    small and always replaced; an image already in the bucket is skipped, so rerunning after an interruption resumes.
    """

    def __init__(self, store: DatasetStore) -> None:
        self._store = store

    async def upload(self, dataroot: str, version: str, cameras: Sequence[str]) -> UploadResult:
        root = Path(dataroot)
        tables, images = await asyncio.to_thread(_find_files, root, version, cameras)
        uploaded = await self._store.upload_all({_key(root, path): path for path in tables}, skip_existing=False)
        uploaded += await self._store.upload_all({_key(root, path): path for path in images}, skip_existing=True)
        skipped = len(tables) + len(images) - uploaded
        logger.bind(uploaded=uploaded, skipped=skipped).info("dataset uploaded")
        return UploadResult(uploaded, skipped)


def _find_files(root: Path, version: str, cameras: Sequence[str]) -> tuple[list[Path], list[Path]]:
    if not (root / version).is_dir():
        raise FileNotFoundError(
            f"No {version!r} tables in {root}: nothing to upload (run `backseat-driver describe` once?)"
        )
    tables = list(_files(root, f"{version}/"))
    images = [path for camera in cameras for path in _files(root, f"samples/{camera}/")]
    return tables, images


def _files(root: Path, prefix: str) -> Iterator[Path]:
    yield from sorted(path for path in (root / prefix).rglob("*") if path.is_file())


def _key(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
