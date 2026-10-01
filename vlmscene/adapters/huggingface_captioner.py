"""HuggingFace adapter for the `Captioner` port.

Wraps the `transformers` `image-to-text` pipeline. Any captioning checkpoint from
the HuggingFace hub works; the default is a small BLIP model. `load()` and
`caption()` are separate so a caller can choose to eager-load at process startup
(so a readiness probe means something) or let `caption()` load lazily on first use.
"""

from typing import Any

from vlmscene.bl.captioner import Captioner


class HuggingFaceCaptioner(Captioner):
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
        return result[0]["generated_text"].strip()

    def healthcheck(self) -> bool:
        # Always True: the model loads lazily on first caption, and /ready must
        # not report unready before then.
        return True
