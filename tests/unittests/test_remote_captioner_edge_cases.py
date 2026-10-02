"""Edge cases of the Anthropic and Ollama captioners beyond their happy paths (see their own test modules)."""

import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from backseat_driver.adapters.anthropic_captioner import AnthropicCaptioner
from backseat_driver.adapters.ollama_captioner import OllamaCaptioner


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


def test_anthropic_load_is_a_noop_for_the_hosted_model() -> None:
    assert AnthropicCaptioner(api_key="k").load() is None


def test_anthropic_model_name_is_the_configured_model() -> None:
    assert AnthropicCaptioner(api_key="k", model_name="claude-test").model_name == "claude-test"


def test_anthropic_healthcheck_is_true_when_the_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        return _FakeResponse(b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    healthy = AnthropicCaptioner(api_key="secret", base_url="https://api.test/").healthcheck()

    assert healthy is True
    assert seen["url"] == "https://api.test/v1/models?limit=1"
    assert seen["headers"]["X-api-key"] == "secret"


def test_anthropic_healthcheck_is_false_when_the_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.HTTPError(request.full_url, HTTPStatus.UNAUTHORIZED, "Unauthorized", Message(), None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert AnthropicCaptioner(api_key="bad").healthcheck() is False


def test_anthropic_healthcheck_is_false_on_a_non_200_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(b"{}")
    response.status = HTTPStatus.NO_CONTENT
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: response)

    assert AnthropicCaptioner(api_key="k").healthcheck() is False


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("a.jpg", "image/jpeg"),
        ("a.jpeg", "image/jpeg"),
        ("a.png", "image/png"),
        ("a.gif", "image/gif"),
        ("a.webp", "image/webp"),
        ("UPPER.JPG", "image/jpeg"),
    ],
)
def test_anthropic_tags_each_supported_image_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, filename: str, media_type: str
) -> None:
    path = tmp_path / filename
    path.write_bytes(b"x")
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        seen["body"] = json.loads(request.data)  # ty: ignore[invalid-argument-type]
        return _FakeResponse(b'{"content": [{"type": "text", "text": "ok"}]}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    AnthropicCaptioner(api_key="k").caption(str(path))

    assert seen["body"]["messages"][0]["content"][0]["source"]["media_type"] == media_type


def test_anthropic_ignores_non_text_blocks_and_strips_the_joined_text(
    monkeypatch: pytest.MonkeyPatch, image_path: str
) -> None:
    body = json.dumps(
        {
            "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": " one "},
                {"type": "text", "text": "two "},
            ]
        }
    ).encode()
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: _FakeResponse(body))

    assert AnthropicCaptioner(api_key="k").caption(image_path) == "one two"


def test_anthropic_reports_an_unreachable_service(monkeypatch: pytest.MonkeyPatch, image_path: str) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Cannot reach Anthropic"):
        AnthropicCaptioner(api_key="k").caption(image_path)


def test_anthropic_caption_of_a_missing_file_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        AnthropicCaptioner(api_key="k").caption(str(tmp_path / "missing.jpg"))


def test_ollama_load_is_a_noop_because_the_server_owns_the_model() -> None:
    assert OllamaCaptioner().load() is None


def test_ollama_model_name_is_the_configured_model() -> None:
    assert OllamaCaptioner(model_name="llava:13b").model_name == "llava:13b"


def test_ollama_caption_of_a_missing_file_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OllamaCaptioner().caption(str(tmp_path / "missing.png"))
