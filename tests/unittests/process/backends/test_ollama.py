import base64
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


def test_caption_posts_the_model_prompt_and_image_and_returns_the_stripped_response(image_path: str) -> None:
    http = FakeHttpClient(response={"response": "  a long, detailed description  "})
    backend = OllamaBackend(http, base_url="http://ollama:11434/")

    description = backend.generate(image_path, CaptionModel("llava", prompt="list the road users"))

    assert description == "a long, detailed description"
    (posted,) = http.posts
    assert posted.url == "http://ollama:11434/api/generate"
    assert posted.service == "Ollama"
    assert posted.payload == {
        "model": "llava",
        "prompt": "list the road users",
        "images": [base64.b64encode(b"fake-image-bytes").decode()],
        "stream": False,
    }


def test_caption_of_a_missing_file_fails_fast_without_calling_the_server(tmp_path: Path) -> None:
    http = FakeHttpClient()

    with pytest.raises(FileNotFoundError):
        OllamaBackend(http).generate(str(tmp_path / "missing.png"), CaptionModel("llava"))

    assert http.posts == []


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
