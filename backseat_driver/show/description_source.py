"""Where a report's descriptions and images come from.

A source hands over `SceneDescription`s and can produce the bytes of the image each one points at, because only the
source knows what its `image_path` means (a local file, a dataset key the API serves). Keeping that pairing here is what
lets the CLI and the UI build their pages the same way, whatever mix of sources they read.
"""

from abc import ABC, abstractmethod

from backseat_driver.models import SceneDescription
from backseat_driver.process.http_client import HttpResponse


class DescriptionSource(ABC):
    @abstractmethod
    async def descriptions(self) -> list[SceneDescription]:
        """Everything this source has, read afresh on each call."""

    @abstractmethod
    async def image(self, image_path: str) -> HttpResponse:
        """The bytes behind one of this source's own `image_path`s."""

    @abstractmethod
    def image_link(self, image_path: str) -> str | None:
        """A URL on the serving UI that answers with the image, or None when the image can only be embedded."""
