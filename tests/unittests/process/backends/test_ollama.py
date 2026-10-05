from pathlib import Path

import pytest

from backseat_driver.process.backends.ollama import OllamaBackend
from backseat_driver.process.model import CaptionModel
from tests.fakes import FakeHttpClient


@pytest.fixture
def image_path(tmp_path: Path) -> str:
    path = tmp_path / "scene.png"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_caption_posts_prompt_and_image_and_returns_stripped_response(image_path: str) -> None:
    http = FakeHttpClient(response={"response": "  a long, detailed description  "})
    backend = OllamaBackend(http, base_url="http://ollama:11434/")

    description = backend.generate(image_path, CaptionModel("llava"))

    assert description == "a long, detailed description"
    (posted,) = http.posts
    assert posted.url == "http://ollama:11434/api/generate"
    assert posted.service == "Ollama"
    assert posted.payload["model"] == "llava"
    assert posted.payload["stream"] is False
    assert len(posted.payload["images"]) == 1


def test_caption_limits_generated_tokens(image_path: str) -> None:
    http = FakeHttpClient(response={"response": "wet road", "done_reason": "stop"})
    backend = OllamaBackend(http, max_tokens=64)

    backend.generate(image_path, CaptionModel("llava"))

    (posted,) = http.posts
    assert posted.payload["options"] == {"num_predict": 64}


def test_caption_fails_when_generation_hits_the_token_limit(image_path: str) -> None:
    http = FakeHttpClient(response={"response": "road, road, road, road", "done_reason": "length"})
    backend = OllamaBackend(http, max_tokens=64)

    with pytest.raises(RuntimeError, match=r"hit the 64-token limit on .*scene\.png"):
        backend.generate(image_path, CaptionModel("llava"))


def test_caption_propagates_http_failures(image_path: str) -> None:
    backend = OllamaBackend(FakeHttpClient(error=RuntimeError("Cannot reach Ollama at http://x: refused")))

    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        backend.generate(image_path, CaptionModel("llava"))


def test_healthcheck_probes_the_tags_endpoint() -> None:
    http = FakeHttpClient()

    OllamaBackend(http, base_url="http://ollama:11434/").healthcheck()

    assert [probe.url for probe in http.probes] == ["http://ollama:11434/api/tags"]


@pytest.mark.parametrize("reachable", [True, False])
def test_healthcheck_reports_whether_the_server_is_reachable(reachable: bool) -> None:
    backend = OllamaBackend(FakeHttpClient(reachable=reachable))

    assert backend.healthcheck() is reachable
