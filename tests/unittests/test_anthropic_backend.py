import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from backseat_driver.captioning.anthropic_backend import AnthropicBackend
from backseat_driver.captioning.model import CaptionModel

_MODEL = CaptionModel("claude-test")


class _FakeResponse(io.BytesIO):
    status = HTTPStatus.OK

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:  # ty: ignore[invalid-method-override]
        self.close()


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.jpg"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_caption_sends_image_prompt_and_auth_and_joins_text_blocks(
    monkeypatch: pytest.MonkeyPatch, image_path: str
) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = json.loads(bytes(request.data))  # ty: ignore[invalid-argument-type]
        content = [{"type": "text", "text": "  A wet two-lane road. "}, {"type": "text", "text": "Rain falls.  "}]
        return _FakeResponse(json.dumps({"content": content}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    backend = AnthropicBackend(api_key="test-key")

    description = backend.generate(image_path, _MODEL)

    assert description == "A wet two-lane road. Rain falls."
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["body"]["model"] == "claude-test"
    image_block = seen["body"]["messages"][0]["content"][0]
    assert image_block["source"]["media_type"] == "image/jpeg"


def test_caption_rejects_unsupported_image_type(tmp_path: Path) -> None:
    path = tmp_path / "scene.bmp"
    path.write_bytes(b"x")

    with pytest.raises(ValueError, match="Unsupported image type"):
        AnthropicBackend(api_key="test-key").generate(str(path), _MODEL)


def test_caption_raises_with_api_error_body(monkeypatch: pytest.MonkeyPatch, image_path: str) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.HTTPError(
            request.full_url,
            HTTPStatus.UNAUTHORIZED,
            "Unauthorized",
            Message(),
            io.BytesIO(b'{"error":"invalid x-api-key"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="invalid x-api-key"):
        AnthropicBackend(api_key="bad").generate(image_path, _MODEL)


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        AnthropicBackend(api_key="")


def test_healthcheck_is_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert AnthropicBackend(api_key="k").healthcheck() is False
