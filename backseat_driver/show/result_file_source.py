"""Descriptions from the JSON files `describe` writes; `image_path` is a dataset key the `ImageStore` resolves."""

import json
import mimetypes
from collections.abc import Sequence
from pathlib import Path

from backseat_driver.models import SceneDescription
from backseat_driver.process.http_client import HttpResponse
from backseat_driver.read.images.image_store import ImageStore
from backseat_driver.show.description_source import DescriptionSource


class ResultFileSource(DescriptionSource):
    def __init__(self, paths: Sequence[Path], images: ImageStore) -> None:
        self._paths = list(paths)
        self._images = images

    @classmethod
    def in_directory(cls, directory: Path, images: ImageStore) -> "ResultFileSource":
        """Every `*.json` in `directory` as of now."""
        return cls(sorted(directory.glob("*.json")), images)

    def descriptions(self) -> list[SceneDescription]:
        return [
            SceneDescription.model_validate(item)
            for path in self._paths
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def image(self, image_path: str) -> HttpResponse:
        """Raises FileNotFoundError if the dataset no longer has the image."""
        with self._images.local_copy(self._images.uri_for(image_path)) as path:
            return HttpResponse(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

    def image_link(self, image_path: str) -> str | None:
        return None
