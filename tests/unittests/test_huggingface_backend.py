import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from backseat_driver.captioning.huggingface_backend import HuggingFaceBackend
from backseat_driver.captioning.model import CaptionModel


def test_healthcheck_returns_true() -> None:
    backend = HuggingFaceBackend()

    assert backend.healthcheck() is True


@pytest.fixture
def fake_transformers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stubs `transformers.pipeline` so no model is ever downloaded in tests."""
    call_count: list[str] = []

    def fake_pipeline_factory(task: str, model: str) -> object:
        call_count.append(model)

        def _run(image: Image.Image) -> list[dict[str, str]]:
            return [{"generated_text": f"  a caption from {model}  "}]

        return _run

    fake_module = types.SimpleNamespace(pipeline=fake_pipeline_factory)
    monkeypatch.setitem(sys.modules, "transformers", fake_module)
    return call_count


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.png"
    Image.new("RGB", (4, 4), color="red").save(path)
    return str(path)


def test_generate_returns_stripped_generated_text(image_path: str, fake_transformers: list[str]) -> None:
    backend = HuggingFaceBackend()

    description = backend.generate(image_path, CaptionModel("fake/model"))

    assert description == "a caption from fake/model"


def test_generate_loads_pipeline_once_per_model(image_path: str, fake_transformers: list[str]) -> None:
    backend = HuggingFaceBackend()
    model = CaptionModel("fake/model")

    backend.generate(image_path, model)
    backend.generate(image_path, model)

    assert fake_transformers == ["fake/model"]


def test_one_backend_serves_several_models(image_path: str, fake_transformers: list[str]) -> None:
    backend = HuggingFaceBackend()

    first = backend.generate(image_path, CaptionModel("model/a"))
    second = backend.generate(image_path, CaptionModel("model/b"))

    assert (first, second) == ("a caption from model/a", "a caption from model/b")
    assert fake_transformers == ["model/a", "model/b"]
