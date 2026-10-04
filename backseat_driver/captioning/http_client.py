"""Port for the HTTP calls made by the caption backends and the report builder, plus its stdlib adapter."""

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class HttpStatusError(RuntimeError):
    """The server answered with an error status; `status` is its code."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


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
    def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
        """GET `url` and return the body, raising RuntimeError on any failure."""

    @abstractmethod
    def is_reachable(self, url: str, headers: dict[str, str], timeout: float) -> bool:
        """True if a GET of `url` answers 200; any connection or HTTP error is False."""


class UrllibHttpClient(HttpClient):
    """`HttpClient` over the standard library's urllib."""

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
                return response.status == 200
        except OSError:
            return False
