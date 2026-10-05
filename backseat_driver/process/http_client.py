"""Port for the HTTP calls made by the caption backends and the report builder, plus its stdlib adapter."""

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from backseat_driver.errors import HttpStatusError


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    content_type: str


class HttpClient(ABC):
    """The HTTP interactions the callers need, so tests can swap the network out."""

    @abstractmethod
    def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float, service: str
    ) -> dict[str, Any]:
        """POST `payload` as JSON and return the decoded response, raising RuntimeError on any failure."""

    @abstractmethod
    async def post_json_async(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service: str
    ) -> dict[str, Any]:
        """`post_json` for many calls in flight on one event loop; the caller bounds it with `asyncio.timeout`."""

    @abstractmethod
    def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
        """GET `url` and return the body, raising RuntimeError on any failure."""

    @abstractmethod
    def is_reachable(self, url: str, headers: dict[str, str], timeout: float) -> bool:
        """True if a GET of `url` answers 200; any connection or HTTP error is False."""

    @abstractmethod
    async def is_reachable_async(self, url: str, headers: dict[str, str]) -> bool:
        """`is_reachable` on the event loop; the caller bounds it with `asyncio.timeout`."""


class UrllibHttpClient(HttpClient):
    """`HttpClient` over the standard library's urllib, except `post_json_async`: urllib cannot do a non-blocking
    request, so that one goes through httpx, with the same error messages."""

    async def post_json_async(
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

    def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float, service: str
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"{service} returned HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {service} at {url}: {exc.reason}") from exc

    async def is_reachable_async(self, url: str, headers: dict[str, str]) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                return (await client.get(url, headers=headers)).status_code == HTTPStatus.OK
        except httpx.HTTPError:
            return False

    def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                return HttpResponse(response.read(), response.headers.get_content_type())
        except urllib.error.HTTPError as exc:
            raise HttpStatusError(
                exc.code, f"{service} returned HTTP {exc.code}: {exc.read().decode(errors='replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {service} at {url}: {exc.reason}") from exc

    def is_reachable(self, url: str, headers: dict[str, str], timeout: float) -> bool:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                return response.status == HTTPStatus.OK
        except OSError:
            return False
