import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from backseat_driver.captioning.model import CaptionModel
from backseat_driver.captioning.ollama_backend import OllamaBackend


class _FakeResponse(io.BytesIO):
    status = HTTPStatus.OK

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:  # ty: ignore[invalid-method-override]
        self.close()


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.png"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_caption_posts_prompt_and_image_and_returns_stripped_response(
    monkeypatch: pytest.MonkeyPatch, image_path: str
) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        seen["url"] = request.full_url
        seen["body"] = json.loads(bytes(request.data))  # ty: ignore[invalid-argument-type]
        return _FakeResponse(json.dumps({"response": "  a long, detailed description  "}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    backend = OllamaBackend(base_url="http://ollama:11434/")

    description = backend.generate(image_path, CaptionModel("llava"))

    assert description == "a long, detailed description"
    assert seen["url"] == "http://ollama:11434/api/generate"
    assert seen["body"]["model"] == "llava"
    assert seen["body"]["stream"] is False
    assert len(seen["body"]["images"]) == 1


def test_caption_raises_when_server_unreachable(monkeypatch: pytest.MonkeyPatch, image_path: str) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        OllamaBackend().generate(image_path, CaptionModel("llava"))


def test_caption_raises_with_server_error_body(monkeypatch: pytest.MonkeyPatch, image_path: str) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.HTTPError(
            request.full_url, HTTPStatus.NOT_FOUND, "Not Found", Message(), io.BytesIO(b'{"error":"model not found"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="model not found"):
        OllamaBackend().generate(image_path, CaptionModel("llava"))


def test_healthcheck_is_false_when_server_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert OllamaBackend().healthcheck() is False


def test_healthcheck_is_true_when_server_responds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _FakeResponse(b"{}"))

    assert OllamaBackend().healthcheck() is True
