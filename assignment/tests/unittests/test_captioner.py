import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from vlm_scene_description.bl.captioner import BlipCaptioner


def test_model_name_returns_configured_name() -> None:
    captioner = BlipCaptioner(model_name="some/model")

    assert captioner.model_name == "some/model"


def test_healthcheck_returns_true() -> None:
    captioner = BlipCaptioner()

    assert captioner.healthcheck() is True


@pytest.fixture
def fake_transformers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stubs `transformers.pipeline` so no model is ever downloaded in tests."""
    call_count: list[str] = []

    def fake_pipeline_factory(task: str, model: str) -> object:
        call_count.append(model)

        def _run(image: Image.Image) -> list[dict[str, str]]:
            return [{"generated_text": "  a fake caption  "}]

        return _run

    fake_module = types.SimpleNamespace(pipeline=fake_pipeline_factory)
    monkeypatch.setitem(sys.modules, "transformers", fake_module)
    return call_count


def test_caption_returns_stripped_generated_text(tmp_path: Path, fake_transformers: list[str]) -> None:
    image_path = tmp_path / "scene.png"
    Image.new("RGB", (4, 4), color="red").save(image_path)
    captioner = BlipCaptioner(model_name="fake/model")

    description = captioner.caption(str(image_path))

    assert description == "a fake caption"


def test_caption_loads_pipeline_once_and_caches(tmp_path: Path, fake_transformers: list[str]) -> None:
    image_path = tmp_path / "scene.png"
    Image.new("RGB", (4, 4), color="red").save(image_path)
    captioner = BlipCaptioner(model_name="fake/model")

    captioner.caption(str(image_path))
    captioner.caption(str(image_path))

    assert fake_transformers == ["fake/model"]
