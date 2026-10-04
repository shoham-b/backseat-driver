"""Finds the keyframes of a dataset that lives in object storage.

Ingest never needs the images, only the metadata tables (`<version>/*.json`) the devkit reads to walk the scenes, so
those are downloaded to a scratch directory and the devkit loader runs over them. Each keyframe's `image_path` is
reported as its dataset-relative key, the string the `DatasetStore` also addresses the image by; the scratch directory
itself is gone by the time anyone sees a keyframe.
"""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from backseat_driver.models import SceneKeyframe
from backseat_driver.read.relative_scene_loader import RelativeSceneLoader
from backseat_driver.read.s3.dataset_store import DatasetStore
from backseat_driver.read.scene_loader import SceneLoader


class StoredSceneLoader(SceneLoader):
    def __init__(self, store: DatasetStore, version: str, make_loader: Callable[[str], SceneLoader]) -> None:
        """`make_loader` builds the real loader over a local dataroot holding only the metadata tables."""
        self._store = store
        self._version = version
        self._make_loader = make_loader

    def load_keyframes(self) -> list[SceneKeyframe]:
        with TemporaryDirectory(prefix="backseat-driver-tables-") as directory:
            self._store.download_prefix(f"{self._version}/", Path(directory) / self._version)
            return RelativeSceneLoader(self._make_loader(directory), directory).load_keyframes()
