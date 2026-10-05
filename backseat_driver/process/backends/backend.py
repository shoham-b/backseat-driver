"""Port for the platform that runs a captioning model (HuggingFace, Ollama, Anthropic).

A backend knows how to reach and drive a runtime; which model it runs is a
`CaptionModel` handed in per call. `BackendCaptioner` pairs the two. Every method is a coroutine: a backend that
blocks (local inference) moves that work to a worker thread, one that waits on the network just awaits it.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from backseat_driver.process.model import CaptionModel


class CaptionBackend(ABC):
    """A runtime that can run captioning models on images."""

    @abstractmethod
    async def load(self, model: CaptionModel) -> None:
        """Make `model` ready to serve. Safe to call more than once."""

    @abstractmethod
    async def generate(self, image_path: str, model: CaptionModel) -> str:
        """Describe the image at `image_path` with `model`."""

    async def generate_many(self, image_paths: Sequence[str], model: CaptionModel) -> list[str]:
        """Describe each image, in order. Override to run them together; this one runs them one by one."""
        return [await self.generate(image_path, model) for image_path in image_paths]

    @abstractmethod
    async def healthcheck(self) -> bool:
        """True if the runtime can serve requests.

        Models load lazily on the first `generate()` call, so this does not imply
        any model is loaded; a load failure surfaces from `generate()`.
        """
