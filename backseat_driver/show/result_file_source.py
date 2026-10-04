"""Descriptions from the JSON files `describe` writes; their images are local files named by `image_path`."""

import json
import mimetypes
from collections.abc import Sequence
from pathlib import Path

from backseat_driver.models import SceneDescription
from backseat_driver.process.http_client import HttpResponse
from backseat_driver.show.description_source import DescriptionSource


class ResultFileSource(DescriptionSource):
    def __init__(self, paths: Sequence[Path]) -> None:
        self._paths = list(paths)

    @classmethod
    def in_directory(cls, directory: Path) -> "ResultFileSource":
        """Every `*.json` in `directory` as of now."""
        return cls(sorted(directory.glob("*.json")))

    def descriptions(self) -> list[SceneDescription]:
        return [
            SceneDescription.model_validate(item)
            for path in self._paths
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def image(self, image_path: str) -> HttpResponse:
        """Raises FileNotFoundError if the image is gone from disk."""
        image = Path(image_path)
        return HttpResponse(image.read_bytes(), mimetypes.guess_type(image.name)[0] or "application/octet-stream")

    def image_link(self, image_path: str) -> str | None:
        return None
