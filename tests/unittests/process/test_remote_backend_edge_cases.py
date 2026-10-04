"""Edge cases of the Anthropic and Ollama backends beyond their happy paths (see their own test modules)."""

from pathlib import Path

import pytest

from backseat_driver.process.anthropic_backend import AnthropicBackend
from backseat_driver.process.model import CaptionModel
from backseat_driver.process.ollama_backend import OllamaBackend
from tests.fakes import FakeHttpClient

_MODEL = CaptionModel("test-model")


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.jpg"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_anthropic_load_is_a_noop_for_the_hosted_model() -> None:
    assert AnthropicBackend(FakeHttpClient(), api_key="k").load(_MODEL) is None


def test_anthropic_healthcheck_lists_models_with_the_key() -> None:
    http = FakeHttpClient()

    AnthropicBackend(http, api_key="secret", base_url="https://api.test/").healthcheck()

    (probe,) = http.probes
    assert probe.url == "https://api.test/v1/models?limit=1"
    assert probe.headers["x-api-key"] == "secret"


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
def test_anthropic_tags_each_supported_image_type(tmp_path: Path, filename: str, media_type: str) -> None:
    path = tmp_path / filename
    path.write_bytes(b"x")
    http = FakeHttpClient(response={"content": [{"type": "text", "text": "ok"}]})

    AnthropicBackend(http, api_key="k").generate(str(path), _MODEL)

    assert http.posts[0].payload["messages"][0]["content"][0]["source"]["media_type"] == media_type


def test_anthropic_ignores_non_text_blocks_and_strips_the_joined_text(image_path: str) -> None:
    content = [
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": " one "},
        {"type": "text", "text": "two "},
    ]
    backend = AnthropicBackend(FakeHttpClient(response={"content": content}), api_key="k")

    assert backend.generate(image_path, _MODEL) == "one two"


def test_anthropic_caption_of_a_missing_file_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        AnthropicBackend(FakeHttpClient(), api_key="k").generate(str(tmp_path / "missing.jpg"), _MODEL)


def test_ollama_load_is_a_noop_because_the_server_owns_the_model() -> None:
    assert OllamaBackend(FakeHttpClient()).load(_MODEL) is None


def test_ollama_caption_of_a_missing_file_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        OllamaBackend(FakeHttpClient()).generate(str(tmp_path / "missing.png"), _MODEL)
