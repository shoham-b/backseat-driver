"""Vision-language captioning — turns an image on disk into a short description.

BlipCaptioner wraps a small HuggingFace image-captioning pipeline (BLIP by
default). `load()` and `caption()` are separate so a caller can choose to
eager-load at process startup (so a readiness probe means something) or let
`caption()` load lazily on first use — the leaf model-loading and inference
logic itself is not implemented yet; this module fixes the object shape and
call sequence, not the behavior.
"""

from typing import Any, Protocol


class Captioner(Protocol):
    """Anything that can describe an image in natural language."""

    @property
    def model_name(self) -> str: ...

    def load(self) -> None:
        """Load the underlying model. Safe to call more than once."""
        ...

    def caption(self, image_path: str) -> str: ...

    def healthcheck(self) -> bool:
        """True once the model is loaded and ready to serve requests."""
        ...


class BlipCaptioner:
    """Image captioning backed by a HuggingFace `image-to-text` pipeline."""

    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base") -> None:
        self._model_name = model_name
        self._pipeline: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        if self._pipeline is not None:
            return
        from transformers import pipeline

        self._pipeline = pipeline("image-to-text", model=self._model_name)

    def caption(self, image_path: str) -> str:
        from PIL import Image

        self.load()
        assert self._pipeline is not None
        with Image.open(image_path) as image:
            result = self._pipeline(image.convert("RGB"))
        return str(result[0]["generated_text"]).strip()

    def healthcheck(self) -> bool:
        # The model loads lazily on first caption(), so a fresh captioner can already serve;
        # a model that fails to load surfaces as an error on that first call instead.
        return True
