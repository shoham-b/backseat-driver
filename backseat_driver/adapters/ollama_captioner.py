"""Ollama adapter for the `Captioner` port.

Talks to a local Ollama server over HTTP, so no model weights or ML libraries are
loaded in-process. Unlike the HuggingFace BLIP pipeline, a multimodal Ollama model
(e.g. `llava`, `llama3.2-vision`) takes a prompt, which makes its descriptions far
more verbose and steerable.
"""

import base64
import urllib.request
from pathlib import Path

from backseat_driver.adapters._http import DETAILED_SCENE_PROMPT, post_json
from backseat_driver.bl.captioner import Captioner


class OllamaCaptioner(Captioner):
    """Image captioning backed by a multimodal model served by Ollama."""

    def __init__(
        self,
        model_name: str = "llava",
        base_url: str = "http://localhost:11434",
        prompt: str = DETAILED_SCENE_PROMPT,
        timeout: float = 300.0,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._prompt = prompt
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        # The Ollama server owns the model lifecycle and loads it on the first request.
        return

    def caption(self, image_path: str) -> str:
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        payload = {"model": self._model_name, "prompt": self._prompt, "images": [image_b64], "stream": False}
        body = post_json(f"{self._base_url}/api/generate", payload, {}, self._timeout, "Ollama")
        return body["response"].strip()

    def healthcheck(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base_url}/api/tags", timeout=5) as response:
                return response.status == 200
        except OSError:
            return False
