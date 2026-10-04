from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from backseat_driver.process.huggingface_backend import HuggingFaceBackend
from backseat_driver.process.model import CaptionModel


class _FakePipelineFactory:
    """Stands in for `transformers.pipeline` so no model is ever downloaded; records the models it was asked for."""

    def __init__(self) -> None:
        self.models: list[str] = []

    def __call__(self, model_name: str) -> Callable[..., Any]:
        self.models.append(model_name)

        def run(image: Image.Image) -> list[dict[str, str]]:
            return [{"generated_text": f"  a caption from {model_name}  "}]

        return run


def test_healthcheck_returns_true() -> None:
    backend = HuggingFaceBackend(_FakePipelineFactory())

    assert backend.healthcheck() is True


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.png"
    Image.new("RGB", (4, 4), color="red").save(path)
    return str(path)


def test_generate_returns_stripped_generated_text(image_path: str) -> None:
    backend = HuggingFaceBackend(_FakePipelineFactory())

    description = backend.generate(image_path, CaptionModel("fake/model"))

    assert description == "a caption from fake/model"


def test_generate_loads_pipeline_once_per_model(image_path: str) -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)
    model = CaptionModel("fake/model")

    backend.generate(image_path, model)
    backend.generate(image_path, model)

    assert factory.models == ["fake/model"]


def test_one_backend_serves_several_models(image_path: str) -> None:
    factory = _FakePipelineFactory()
    backend = HuggingFaceBackend(factory)

    first = backend.generate(image_path, CaptionModel("model/a"))
    second = backend.generate(image_path, CaptionModel("model/b"))

    assert (first, second) == ("a caption from model/a", "a caption from model/b")
    assert factory.models == ["model/a", "model/b"]
