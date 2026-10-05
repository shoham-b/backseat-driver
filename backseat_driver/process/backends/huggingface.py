"""HuggingFace backend for the `CaptionBackend` port.

Wraps the `transformers` `image-to-text` pipeline. Any captioning checkpoint from
the HuggingFace hub works as the model; the default is a small BLIP model. `load()`
and `generate()` are separate so a caller can choose to eager-load at process
startup (so a readiness probe means something) or let `generate()` load lazily on
first use. One pipeline is kept per model name.
"""

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from backseat_driver.errors import UnprocessableError
from backseat_driver.process.backends.backend import CaptionBackend
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


def _open_rgb(image_path: str) -> Any:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(image_path) as image:
            return image.convert("RGB")
    except UnidentifiedImageError as exc:
        raise UnprocessableError(f"could not read image: {exc}") from exc


class HuggingFaceBackend(CaptionBackend):
    """Runs models through a local HuggingFace `image-to-text` pipeline."""

    def __init__(self, pipeline_factory: PipelineFactory = transformers_pipeline) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipelines: dict[str, Callable[..., Any]] = {}

    # Loading and inference block (disk, CPU or GPU), so each runs on a worker thread and leaves the event loop free.

    async def load(self, model: CaptionModel) -> None:
        await asyncio.to_thread(self._load, model)

    async def generate(self, image_path: str, model: CaptionModel) -> str:
        return await asyncio.to_thread(self._generate_one, image_path, model)

    async def generate_many(self, image_paths: Sequence[str], model: CaptionModel) -> list[str]:
        """One forward pass over the whole batch: on CPU about twice the throughput of captioning one by one."""
        return await asyncio.to_thread(self._generate_batch, image_paths, model)

    def _load(self, model: CaptionModel) -> None:
        if model.name in self._pipelines:
            return
        self._pipelines[model.name] = self._pipeline_factory(model.name)

    def _generate_one(self, image_path: str, model: CaptionModel) -> str:
        self._load(model)
        result = self._pipelines[model.name](_open_rgb(image_path))
        return result[0]["generated_text"].strip()

    def _generate_batch(self, image_paths: Sequence[str], model: CaptionModel) -> list[str]:
        if not image_paths:
            return []
        self._load(model)
        results = self._pipelines[model.name]([_open_rgb(path) for path in image_paths], batch_size=len(image_paths))
        return [result[0]["generated_text"].strip() for result in results]

    async def healthcheck(self) -> bool:
        # Always True: models load lazily on first use, and /ready must
        # not report unready before then.
        return True
