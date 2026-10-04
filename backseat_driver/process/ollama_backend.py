"""Ollama backend for the `CaptionBackend` port.

Talks to a local Ollama server over HTTP, so no model weights or ML libraries are
loaded in-process. Unlike the HuggingFace BLIP pipeline, a multimodal Ollama model
(e.g. `llava`, `llama3.2-vision`) takes a prompt, which makes its descriptions far
more verbose and steerable.
"""

import base64
from pathlib import Path

from backseat_driver.process.backend import CaptionBackend
from backseat_driver.process.http_client import HttpClient
from backseat_driver.process.model import CaptionModel


class OllamaBackend(CaptionBackend):
    """Runs models served by an Ollama server."""

    def __init__(self, http: HttpClient, base_url: str = "http://localhost:11434", timeout: float = 300.0) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def load(self, model: CaptionModel) -> None:
        # The Ollama server owns the model lifecycle and loads it on the first request.
        return

    def generate(self, image_path: str, model: CaptionModel) -> str:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        payload = {"model": model.name, "prompt": model.prompt, "images": [image_b64], "stream": False}
        body = self._http.post_json(f"{self._base_url}/api/generate", payload, {}, self._timeout, "Ollama")
        return body["response"].strip()

    def healthcheck(self) -> bool:
        return self._http.is_reachable(f"{self._base_url}/api/tags", {}, 5)
