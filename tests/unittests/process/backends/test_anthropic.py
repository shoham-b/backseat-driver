import base64
from pathlib import Path

import pytest

from backseat_driver.errors import UnprocessableError
from backseat_driver.process.backends.anthropic import AnthropicBackend
from backseat_driver.process.model import CaptionModel
from tests.fakes import FakeHttpClient

_MODEL = CaptionModel("claude-test", prompt="describe the road")


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.jpg"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def _text_response(*texts: str) -> dict[str, object]:
    return {"content": [{"type": "text", "text": text} for text in texts]}


def test_caption_sends_image_prompt_and_auth_and_joins_text_blocks(image_path: str) -> None:
    http = FakeHttpClient(response=_text_response("  A wet two-lane road. ", "Rain falls.  "))
    backend = AnthropicBackend(http, api_key="test-key")

    description = backend.generate(image_path, _MODEL)

    assert description == "A wet two-lane road. Rain falls."
    (posted,) = http.posts
    assert posted.url == "https://api.anthropic.com/v1/messages"
    assert posted.service == "Anthropic"
    assert posted.headers["x-api-key"] == "test-key"
    assert posted.payload["model"] == "claude-test"
    assert "only the caption" in posted.payload["system"]


def test_caption_sends_the_image_bytes_and_the_models_prompt(image_path: str) -> None:
    http = FakeHttpClient(response=_text_response("ok"))

    AnthropicBackend(http, api_key="k").generate(image_path, _MODEL)

    image_block, prompt_block = http.posts[0].payload["messages"][0]["content"]
    assert image_block["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": base64.b64encode(b"fake-image-bytes").decode(),
    }
    assert prompt_block == {"type": "text", "text": "describe the road"}


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
def test_caption_tags_each_supported_image_type(tmp_path: Path, filename: str, media_type: str) -> None:
    path = tmp_path / filename
    path.write_bytes(b"x")
    http = FakeHttpClient(response=_text_response("ok"))

    AnthropicBackend(http, api_key="k").generate(str(path), _MODEL)

    assert http.posts[0].payload["messages"][0]["content"][0]["source"]["media_type"] == media_type


def test_caption_rejects_unsupported_image_type(tmp_path: Path) -> None:
    path = tmp_path / "scene.bmp"
    path.write_bytes(b"x")
    http = FakeHttpClient()

    with pytest.raises(UnprocessableError, match="Unsupported image type"):
        AnthropicBackend(http, api_key="test-key").generate(str(path), _MODEL)

    assert http.posts == []


def test_caption_ignores_non_text_blocks_and_strips_the_joined_text(image_path: str) -> None:
    content = [
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": " one "},
        {"type": "text", "text": "two "},
    ]
    backend = AnthropicBackend(FakeHttpClient(response={"content": content}), api_key="k")

    assert backend.generate(image_path, _MODEL) == "one two"


def test_caption_of_a_missing_file_fails_fast_without_calling_the_api(tmp_path: Path) -> None:
    http = FakeHttpClient()

    with pytest.raises(FileNotFoundError):
        AnthropicBackend(http, api_key="k").generate(str(tmp_path / "missing.jpg"), _MODEL)

    assert http.posts == []


def test_caption_propagates_http_failures(image_path: str) -> None:
    backend = AnthropicBackend(FakeHttpClient(error=RuntimeError("invalid x-api-key")), api_key="bad")

    with pytest.raises(RuntimeError, match="invalid x-api-key"):
        backend.generate(image_path, _MODEL)


def test_an_empty_api_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="api_key"):
        AnthropicBackend(FakeHttpClient(), api_key="")


def test_healthcheck_lists_models_with_the_key() -> None:
    http = FakeHttpClient()

    AnthropicBackend(http, api_key="secret", base_url="https://api.test/").healthcheck()

    (probe,) = http.probes
    assert probe.url == "https://api.test/v1/models?limit=1"
    assert probe.headers["x-api-key"] == "secret"


@pytest.mark.parametrize("reachable", [True, False])
def test_healthcheck_reports_whether_the_api_accepts_the_key(reachable: bool) -> None:
    backend = AnthropicBackend(FakeHttpClient(reachable=reachable), api_key="k")

    assert backend.healthcheck() is reachable
