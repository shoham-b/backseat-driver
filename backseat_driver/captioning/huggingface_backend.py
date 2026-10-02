"""HuggingFace backend for the `CaptionBackend` port.

Wraps the `transformers` `image-to-text` pipeline. Any captioning checkpoint from
the HuggingFace hub works as the model; the default is a small BLIP model. `load()`
and `generate()` are separate so a caller can choose to eager-load at process
startup (so a readiness probe means something) or let `generate()` load lazily on
first use. One pipeline is kept per model name.
"""

from typing import Any

from backseat_driver.captioning.backend import CaptionBackend
from backseat_driver.captioning.model import CaptionModel


class HuggingFaceBackend(CaptionBackend):
    """Runs models through a local HuggingFace `image-to-text` pipeline."""

    def __init__(self) -> None:
        self._pipelines: dict[str, Any] = {}

    def load(self, model: CaptionModel) -> None:
        if model.name in self._pipelines:
            return
        from transformers import pipeline

        self._pipelines[model.name] = pipeline("image-to-text", model=model.name)

    def generate(self, image_path: str, model: CaptionModel) -> str:
        from PIL import Image

        self.load(model)
        with Image.open(image_path) as image:
            result = self._pipelines[model.name](image.convert("RGB"))
        return result[0]["generated_text"].strip()

    def healthcheck(self) -> bool:
        # Always True: models load lazily on first use, and /ready must
        # not report unready before then.
        return True
