"""Port for vision-language captioning — turns an image on disk into a short description.

Platform-specific implementations (HuggingFace, Ollama, Anthropic) live in
`vlmscene.adapters`, so business logic depends only on this abstract class.
"""

from abc import ABC, abstractmethod


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

    @abstractmethod
    def healthcheck(self) -> bool:
        """True if the captioner can serve requests.

        The model loads lazily on the first `caption()` call, so this does not
        imply it is loaded; a load failure surfaces from `caption()`.
        """
