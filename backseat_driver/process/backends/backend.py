"""Port for the platform that runs a captioning model (HuggingFace, Ollama, Anthropic).

A backend knows how to reach and drive a runtime; which model it runs is a
`CaptionModel` handed in per call. `BackendCaptioner` pairs the two.
"""

from abc import ABC, abstractmethod

from backseat_driver.process.model import CaptionModel


class CaptionBackend(ABC):
    """A runtime that can run captioning models on images."""

    @abstractmethod
    def load(self, model: CaptionModel) -> None:
        """Make `model` ready to serve. Safe to call more than once."""

    @abstractmethod
    def generate(self, image_path: str, model: CaptionModel) -> str:
        """Describe the image at `image_path` with `model`."""

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the runtime can serve requests.

        Models load lazily on the first `generate()` call, so this does not imply
        any model is loaded; a load failure surfaces from `generate()`.
        """
