"""Anthropic (Claude) backend for the `CaptionBackend` port.

Calls the hosted Messages API with the image and a prompt, so descriptions are far
more detailed than BLIP's one-liners. Unlike the local backends this needs an API
key and network access at runtime, and each caption is a billed request.

The wait is an awaited HTTP request, so there is no thread, and a batch sends all its requests at once: the time is
spent on the API, not here. The batch size therefore bounds how many requests are in flight. There is no retry, so a
rate limit or a server error fails the batch.
"""

import asyncio
import base64
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backseat_driver.errors import UnprocessableError
from backseat_driver.process.backends.backend import CaptionBackend
from backseat_driver.process.http_client import HttpClient
from backseat_driver.process.model import CaptionModel

_API_VERSION = "2023-06-01"
_HEALTHCHECK_TIMEOUT = 5.0
# A fixed map rather than `mimetypes`, whose table is OS-dependent (e.g. it doesn't know `.webp` on Windows).
_MEDIA_TYPES_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
# Claude otherwise pads answers with preambles and markdown, which breaks the one-line caption contract.
_SYSTEM_PROMPT = (
    "You caption images. Reply with only the caption in the format the user asks for, "
    "with no preamble, no markdown and no line breaks."
)


class AnthropicBackend(CaptionBackend):
    """Runs Claude models through the Anthropic Messages API."""

    def __init__(
        self,
        http: HttpClient,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 512,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicBackend requires a non-empty api_key")
        self._http = http
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout

    async def load(self, model: CaptionModel) -> None:
        # Hosted model: nothing to load locally.
        return

    async def generate(self, image_path: str, model: CaptionModel) -> str:
        return _caption_of(await self._post(image_path, model))

    async def generate_many(self, image_paths: Sequence[str], model: CaptionModel) -> list[str]:
        """One request per image, all in flight at once: the wait is on the API, not on this process."""
        bodies = await asyncio.gather(*(self._post(image_path, model) for image_path in image_paths))
        return [_caption_of(body) for body in bodies]

    async def _post(self, image_path: str, model: CaptionModel) -> dict[str, Any]:
        payload = self._payload(image_path, model)  # reads and encodes one keyframe: quicker than a thread
        try:
            async with asyncio.timeout(self._timeout):
                return await self._http.post_json_async(self._messages_url, payload, self._headers(), "Anthropic")
        except TimeoutError as exc:
            raise RuntimeError(f"Anthropic did not answer within {self._timeout:g} s") from exc

    @property
    def _messages_url(self) -> str:
        return f"{self._base_url}/v1/messages"

    def _payload(self, image_path: str, model: CaptionModel) -> dict[str, Any]:
        media_type = _MEDIA_TYPES_BY_SUFFIX.get(Path(image_path).suffix.lower())
        if media_type is None:
            raise UnprocessableError(f"Unsupported image type for {image_path!r}; expected jpeg/png/gif/webp")
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        return {
            "model": model.name,
            "max_tokens": self._max_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {"type": "text", "text": model.prompt},
                    ],
                }
            ],
        }

    async def healthcheck(self) -> bool:
        # Listing models is free and verifies both reachability and that the key is accepted.
        try:
            async with asyncio.timeout(_HEALTHCHECK_TIMEOUT):
                return await self._http.is_reachable_async(f"{self._base_url}/v1/models?limit=1", self._headers())
        except TimeoutError:
            return False

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "anthropic-version": _API_VERSION}


def _caption_of(body: dict[str, Any]) -> str:
    return "".join(block["text"] for block in body["content"] if block["type"] == "text").strip()
