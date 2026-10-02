import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from backseat_driver.captioning.anthropic_captioner import AnthropicCaptioner
from backseat_driver.captioning.factory import build_captioner
from backseat_driver.config import Settings, VlmBackend


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
    captioner = AnthropicCaptioner(api_key="test-key", model_name="claude-test")

    description = captioner.caption(image_path)

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
        AnthropicCaptioner(api_key="test-key").caption(str(path))


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
        AnthropicCaptioner(api_key="bad").caption(image_path)


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        AnthropicCaptioner(api_key="")


def test_healthcheck_is_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert AnthropicCaptioner(api_key="k").healthcheck() is False


def test_build_captioner_requires_api_key() -> None:
    settings = Settings(anthropic_api_key=None)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_captioner(settings, backend=VlmBackend.ANTHROPIC)


def test_build_captioner_selects_anthropic() -> None:
    settings = Settings(anthropic_api_key=SecretStr("k"), anthropic_model_name="claude-x")

    captioner = build_captioner(settings, backend=VlmBackend.ANTHROPIC)

    assert isinstance(captioner, AnthropicCaptioner)
    assert captioner.model_name == "claude-x"
