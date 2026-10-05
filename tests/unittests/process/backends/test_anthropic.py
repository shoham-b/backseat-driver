from pathlib import Path

import pytest

from backseat_driver.errors import UnprocessableError
from backseat_driver.process.backends.anthropic import AnthropicBackend
from backseat_driver.process.model import CaptionModel
from tests.fakes import FakeHttpClient

_MODEL = CaptionModel("claude-test")


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.jpg"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_caption_sends_image_prompt_and_auth_and_joins_text_blocks(image_path: str) -> None:
    content = [{"type": "text", "text": "  A wet two-lane road. "}, {"type": "text", "text": "Rain falls.  "}]
    http = FakeHttpClient(response={"content": content})
    backend = AnthropicBackend(http, api_key="test-key")

    description = backend.generate(image_path, _MODEL)

    assert description == "A wet two-lane road. Rain falls."
    (posted,) = http.posts
    assert posted.url == "https://api.anthropic.com/v1/messages"
    assert posted.service == "Anthropic"
    assert posted.headers["x-api-key"] == "test-key"
    assert posted.payload["model"] == "claude-test"
    image_block = posted.payload["messages"][0]["content"][0]
    assert image_block["source"]["media_type"] == "image/jpeg"
    assert "only the caption" in posted.payload["system"]


def test_caption_rejects_unsupported_image_type(tmp_path: Path) -> None:
    path = tmp_path / "scene.bmp"
    path.write_bytes(b"x")

    with pytest.raises(UnprocessableError, match="Unsupported image type"):
        AnthropicBackend(FakeHttpClient(), api_key="test-key").generate(str(path), _MODEL)


def test_caption_propagates_http_failures(image_path: str) -> None:
    backend = AnthropicBackend(FakeHttpClient(error=RuntimeError("invalid x-api-key")), api_key="bad")

    with pytest.raises(RuntimeError, match="invalid x-api-key"):
        backend.generate(image_path, _MODEL)


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        AnthropicBackend(FakeHttpClient(), api_key="")


@pytest.mark.parametrize("reachable", [True, False])
def test_healthcheck_reports_whether_the_api_accepts_the_key(reachable: bool) -> None:
    backend = AnthropicBackend(FakeHttpClient(reachable=reachable), api_key="k")

    assert backend.healthcheck() is reachable
