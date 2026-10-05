"""Port for HTTP calls that run concurrently on one event loop, plus its httpx adapter.

Separate from `HttpClient`: that one is blocking and used from plain threads and routes, this one is awaited by a
backend that has many requests in flight at once. It takes no timeout: the caller bounds a call with
`asyncio.timeout`, which also covers the time spent waiting behind other requests.
"""

from abc import ABC, abstractmethod
from typing import Any


class AsyncHttpClient(ABC):
    @abstractmethod
    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service: str
    ) -> dict[str, Any]:
        """POST `payload` as JSON and return the decoded response, raising RuntimeError on any failure."""


class HttpxAsyncHttpClient(AsyncHttpClient):
    """`AsyncHttpClient` over httpx; errors read like `UrllibHttpClient`'s, so callers see the same messages."""

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service: str
    ) -> dict[str, Any]:
        import httpx  # not at module scope: the ingest worker imports the factory and never makes these calls

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise RuntimeError(f"Cannot reach {service} at {url}: {exc}") from exc
        if response.is_error:
            raise RuntimeError(f"{service} returned HTTP {response.status_code}: {response.text}")
        return response.json()
