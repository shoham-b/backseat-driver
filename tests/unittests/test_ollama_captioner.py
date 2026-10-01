import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from vlmscene.adapters.factory import build_captioner
from vlmscene.adapters.huggingface_captioner import HuggingFaceCaptioner
from vlmscene.adapters.ollama_captioner import OllamaCaptioner
from vlmscene.config import Settings, VlmBackend


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
    captioner = OllamaCaptioner(model_name="llava", base_url="http://ollama:11434/")

    description = captioner.caption(image_path)

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
        OllamaCaptioner().caption(image_path)


def test_caption_raises_with_server_error_body(monkeypatch: pytest.MonkeyPatch, image_path: str) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        raise urllib.error.HTTPError(
            request.full_url, HTTPStatus.NOT_FOUND, "Not Found", Message(), io.BytesIO(b'{"error":"model not found"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="model not found"):
        OllamaCaptioner().caption(image_path)


def test_healthcheck_is_false_when_server_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert OllamaCaptioner().healthcheck() is False


def test_healthcheck_is_true_when_server_responds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _FakeResponse(b"{}"))

    assert OllamaCaptioner().healthcheck() is True


def test_build_captioner_defaults_to_huggingface() -> None:
    settings = Settings()

    captioner = build_captioner(settings)

    assert isinstance(captioner, HuggingFaceCaptioner)


def test_build_captioner_selects_ollama_with_configured_model_and_url() -> None:
    settings = Settings(ollama_model_name="llama3.2-vision", ollama_url="http://gpu-box:11434")

    captioner = build_captioner(settings, backend=VlmBackend.OLLAMA)

    assert isinstance(captioner, OllamaCaptioner)
    assert captioner.model_name == "llama3.2-vision"


def test_build_captioner_model_override_wins() -> None:
    settings = Settings()

    captioner = build_captioner(settings, backend=VlmBackend.OLLAMA, model_name="bakllava")

    assert captioner.model_name == "bakllava"
