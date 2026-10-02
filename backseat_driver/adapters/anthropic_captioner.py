"""Anthropic (Claude) adapter for the `Captioner` port.

Calls the hosted Messages API with the image and a prompt, so descriptions are far
more detailed than BLIP's one-liners. Unlike the local backends this needs an API
key and network access at runtime, and each caption is a billed request.
"""

import base64
import urllib.request
from pathlib import Path

from backseat_driver.adapters._http import DETAILED_SCENE_PROMPT, post_json
from backseat_driver.bl.captioner import Captioner

_API_VERSION = "2023-06-01"
# A fixed map rather than `mimetypes`, whose table is OS-dependent (e.g. it doesn't know `.webp` on Windows).
_MEDIA_TYPES_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class AnthropicCaptioner(Captioner):
    """Image captioning backed by a Claude model through the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-haiku-4-5-20251001",
        base_url: str = "https://api.anthropic.com",
        prompt: str = DETAILED_SCENE_PROMPT,
        max_tokens: int = 512,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicCaptioner requires a non-empty api_key")
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._prompt = prompt
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        # Hosted model: nothing to load locally.
        return

    def caption(self, image_path: str) -> str:
        media_type = _MEDIA_TYPES_BY_SUFFIX.get(Path(image_path).suffix.lower())
        if media_type is None:
            raise ValueError(f"Unsupported image type for {image_path!r}; expected jpeg/png/gif/webp")
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        payload = {
            "model": self._model_name,
            "max_tokens": self._max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {"type": "text", "text": self._prompt},
                    ],
                }
            ],
        }
        body = post_json(f"{self._base_url}/v1/messages", payload, self._headers(), self._timeout, "Anthropic")
        return "".join(block["text"] for block in body["content"] if block["type"] == "text").strip()

    def healthcheck(self) -> bool:
        # Listing models is free and verifies both reachability and that the key is accepted.
        request = urllib.request.Request(f"{self._base_url}/v1/models?limit=1", headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status == 200
        except OSError:
            return False

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "anthropic-version": _API_VERSION}
