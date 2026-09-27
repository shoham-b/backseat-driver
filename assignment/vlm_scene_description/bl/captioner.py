"""Vision-language captioning — turns an image on disk into a short description.

BlipCaptioner wraps a small HuggingFace image-captioning pipeline (BLIP by
default). The underlying model is loaded lazily on first use and cached on
the instance, so constructing a BlipCaptioner is cheap even before any
model weights have been downloaded.
"""

from typing import Any, Protocol

from loguru import logger


class Captioner(Protocol):
    """Anything that can describe an image in natural language."""

    def caption(self, image_path: str) -> str: ...

    def healthcheck(self) -> bool: ...


class BlipCaptioner:
    """Image captioning backed by a HuggingFace `image-to-text` pipeline."""

    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base") -> None:
        self._model_name = model_name
        self._pipeline: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def healthcheck(self) -> bool:
        return True

    def caption(self, image_path: str) -> str:
        from PIL import Image

        pipeline = self._get_pipeline()
        image = Image.open(image_path).convert("RGB")
        result = pipeline(image)
        return str(result[0]["generated_text"]).strip()

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from transformers import pipeline as hf_pipeline

            logger.bind(model=self._model_name).info("loading VLM captioning model")
            self._pipeline = hf_pipeline("image-to-text", model=self._model_name)
        return self._pipeline
