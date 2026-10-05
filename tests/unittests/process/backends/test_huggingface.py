from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backseat_driver.errors import UnprocessableError
from backseat_driver.process.backends.huggingface import HuggingFaceBackend
from backseat_driver.process.model import CaptionModel


class _FakePipelineFactory:
    """Stands in for `transformers.pipeline` so no model is ever downloaded; records the models it was asked for."""

    def __init__(self) -> None:
        self.models: list[str] = []
        self.calls: list[tuple[Any, int | None]] = []

    def __call__(self, model_name: str) -> Callable[..., Any]:
        self.models.append(model_name)

        def run(images: Image.Image | list[Image.Image], batch_size: int | None = None) -> Any:
            self.calls.append((images, batch_size))
            caption = [{"generated_text": f"  a caption from {model_name}  "}]
            # Like transformers: one list of candidates per image when given several, a single list for one image.
            return [caption for _ in images] if isinstance(images, list) else caption

        return run


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.png"
    Image.new("RGB", (4, 4), color="red").save(path)
    return str(path)


async def test_generate_returns_stripped_generated_text(image_path: str) -> None:
    backend = HuggingFaceBackend(_FakePipelineFactory())

    description = await backend.generate(image_path, CaptionModel("fake/model"))

    assert description == "a caption from fake/model"


async def test_generate_many_runs_all_images_in_one_batch(image_path: str) -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)

    descriptions = await backend.generate_many([image_path, image_path, image_path], CaptionModel("fake/model"))

    assert descriptions == ["a caption from fake/model"] * 3
    [(images, batch_size)] = factory.calls
    assert len(images) == 3
    assert batch_size == 3


async def test_generate_many_of_nothing_loads_nothing() -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)

    descriptions = await backend.generate_many([], CaptionModel("fake/model"))

    assert descriptions == []
    assert factory.models == []


async def test_generate_many_rejects_the_whole_batch_for_one_unreadable_image(image_path: str, tmp_path: Path) -> None:
    not_an_image = tmp_path / "broken.png"
    not_an_image.write_bytes(b"not an image")
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)

    with pytest.raises(UnprocessableError, match="could not read image"):
        await backend.generate_many([image_path, str(not_an_image)], CaptionModel("fake/model"))

    assert factory.calls == []


async def test_generate_loads_pipeline_once_per_model(image_path: str) -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)
    model = CaptionModel("fake/model")

    await backend.generate(image_path, model)
    await backend.generate(image_path, model)

    assert factory.models == ["fake/model"]


async def test_one_backend_serves_several_models(image_path: str) -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)

    first = await backend.generate(image_path, CaptionModel("model/a"))
    second = await backend.generate(image_path, CaptionModel("model/b"))

    assert (first, second) == ("a caption from model/a", "a caption from model/b")
    assert factory.models == ["model/a", "model/b"]


async def test_a_file_that_is_not_an_image_is_unprocessable(tmp_path: Path) -> None:
    not_an_image = tmp_path / "scene.png"
    not_an_image.write_bytes(b"not an image")
    backend = HuggingFaceBackend(_FakePipelineFactory())

    with pytest.raises(UnprocessableError, match="could not read image"):
        await backend.generate(str(not_an_image), CaptionModel(name="m"))
