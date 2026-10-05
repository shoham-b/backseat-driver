"""The `Captioner` the rest of the code uses: one model run on one backend."""

from collections.abc import Sequence

from backseat_driver.process.backends.backend import CaptionBackend
from backseat_driver.process.captioner import Captioner
from backseat_driver.process.model import CaptionModel


class BackendCaptioner(Captioner):
    """Pairs a `CaptionModel` with the `CaptionBackend` that runs it."""

    def __init__(self, backend: CaptionBackend, model: CaptionModel) -> None:
        self._backend = backend
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model.name

    async def load(self) -> None:
        await self._backend.load(self._model)

    async def caption(self, image_path: str) -> str:
        return await self._backend.generate(image_path, self._model)

    async def caption_many(self, image_paths: Sequence[str]) -> list[str]:
        return await self._backend.generate_many(image_paths, self._model)

    async def healthcheck(self) -> bool:
        return await self._backend.healthcheck()
