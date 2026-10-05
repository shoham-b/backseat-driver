"""Port for vision-language captioning — turns an image on disk into a short description.

The rest of the code depends only on this abstract class. The standard implementation
is `BackendCaptioner`, which pairs a `CaptionBackend` (HuggingFace, Ollama, Anthropic)
with a `CaptionModel`.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class Captioner(ABC):
    """Anything that can describe an image in natural language."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def load(self) -> None:
        """Load the underlying model. Safe to call more than once."""

    @abstractmethod
    def caption(self, image_path: str) -> str: ...

    def caption_many(self, image_paths: Sequence[str]) -> list[str]:
        """Describe each image, in order. Override to run them together; this one runs them one by one."""
        return [self.caption(image_path) for image_path in image_paths]

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the captioner can serve requests.

        The model loads lazily on the first `caption()` call, so this does not
        imply it is loaded; a load failure surfaces from `caption()`.
        """
