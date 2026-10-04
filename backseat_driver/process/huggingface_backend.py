"""HuggingFace backend for the `CaptionBackend` port.

Wraps the `transformers` `image-to-text` pipeline. Any captioning checkpoint from
the HuggingFace hub works as the model; the default is a small BLIP model. `load()`
and `generate()` are separate so a caller can choose to eager-load at process
startup (so a readiness probe means something) or let `generate()` load lazily on
first use. One pipeline is kept per model name.
"""

from collections.abc import Callable
from typing import Any

from backseat_driver.process.backend import CaptionBackend
from backseat_driver.process.model import CaptionModel

PipelineFactory = Callable[[str], Callable[..., Any]]


def transformers_pipeline(model_name: str) -> Callable[..., Any]:
    """Build the `image-to-text` pipeline for `model_name`; `transformers` is imported here, not at module scope."""
    from transformers import pipeline
    from transformers.utils import logging as transformers_logging

    # transformers logs to stderr through its own handler; propagate to the root handler so it matches our format.
    transformers_logging.disable_default_handler()
    transformers_logging.enable_propagation()

    return pipeline("image-to-text", model=model_name)


class HuggingFaceBackend(CaptionBackend):
    """Runs models through a local HuggingFace `image-to-text` pipeline."""

    def __init__(self, pipeline_factory: PipelineFactory = transformers_pipeline) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipelines: dict[str, Callable[..., Any]] = {}

    def load(self, model: CaptionModel) -> None:
        if model.name in self._pipelines:
            return
        self._pipelines[model.name] = self._pipeline_factory(model.name)

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
