"""Port for the HTTP calls made by the caption backends, the API client and the report, plus its httpx adapter."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from backseat_driver.errors import HttpStatusError

if TYPE_CHECKING:
    import httpx

# Sockets, not requests in flight: the batch size is what bounds those. Keep this above it, because a request that
# waits here for a free connection is already inside its caller's `asyncio.timeout`.
DEFAULT_MAX_CONNECTIONS = 100


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    content_type: str


class HttpClient(ABC):
    """The HTTP interactions the callers need, so tests can swap the network out.

    Every call is a coroutine the caller bounds with `asyncio.timeout`: an async function takes no `timeout`.
    """

    @abstractmethod
    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service: str
    ) -> dict[str, Any]:
        """POST `payload` as JSON and return the decoded response, raising RuntimeError on any failure."""

    @abstractmethod
    async def get(self, url: str, headers: dict[str, str], service: str) -> HttpResponse:
        """GET `url` and return the body; raises HttpStatusError on an error status, RuntimeError if unreachable."""

    @abstractmethod
    async def is_reachable(self, url: str, headers: dict[str, str]) -> bool:
        """True if a GET of `url` answers 200; any connection or HTTP error is False."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release the connections. Safe to call again, and on a client that never made a call."""


class HttpxHttpClient(HttpClient):
    """`HttpClient` over one shared `httpx.AsyncClient`, so requests reuse connections instead of handshaking each time.

    The client is created by the first call, never by the constructor. It belongs to the event loop that made that
    call; a call from any other loop raises, rather than failing later inside httpx with 'Event loop is closed'. Whoever
    owns the loop closes the client with `aclose` before the loop ends.
    """

    def __init__(
        self,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        transport: "httpx.AsyncBaseTransport | None" = None,
    ) -> None:
        if max_connections < 1:
            raise ValueError(f"max_connections must be at least 1, got {max_connections}")
        self._max_connections = max_connections
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service: str
    ) -> dict[str, Any]:
        import httpx  # not at module scope: the ingest worker imports the factory and never makes these calls

        client = self._client_for_this_loop()
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise RuntimeError(f"Cannot reach {service} at {url}: {_describe(exc)}") from exc
        if response.is_error:
            raise RuntimeError(f"{service} returned HTTP {response.status_code}: {response.text}")
        return response.json()

    async def get(self, url: str, headers: dict[str, str], service: str) -> HttpResponse:
        import httpx

        client = self._client_for_this_loop()
        try:
            response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise RuntimeError(f"Cannot reach {service} at {url}: {_describe(exc)}") from exc
        if response.is_error:
            raise HttpStatusError(
                response.status_code, f"{service} returned HTTP {response.status_code}: {response.text}"
            )
        content_type = response.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
        return HttpResponse(response.content, content_type)

    async def is_reachable(self, url: str, headers: dict[str, str]) -> bool:
        import httpx

        client = self._client_for_this_loop()
        try:
            return (await client.get(url, headers=headers, follow_redirects=True)).status_code == HTTPStatus.OK
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._client is None:
            return
        self._client_for_this_loop()
        client, self._client, self._loop = self._client, None, None
        await client.aclose()

    def _client_for_this_loop(self) -> "httpx.AsyncClient":
        loop = asyncio.get_running_loop()
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=None,  # the caller bounds each call with `asyncio.timeout`
                limits=httpx.Limits(max_connections=self._max_connections),
                transport=self._transport,
            )
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError(
                "this HttpClient is bound to the event loop that made its first call; close it with `aclose` there "
                "and build another for a new loop (one `asyncio.run` per client)"
            )
        return self._client


def _describe(exc: Exception) -> str:
    # Some transport errors (a refused connection, a timeout) carry no message.
    return str(exc) or type(exc).__name__
