"""`HttpxHttpClient` against a real HTTP server on localhost, and against an `httpx.MockTransport` for what no server
can show (the event-loop guard, the client being created lazily)."""

import asyncio
import json
from collections.abc import Callable
from http import HTTPStatus

import httpx
import pytest

from backseat_driver.errors import HttpStatusError
from backseat_driver.process.http_client import HttpResponse, HttpxHttpClient
from tests.stub_server import Reply, Responder, StubServer

StubFactory = Callable[[Responder], StubServer]


def _always(status: HTTPStatus, body: bytes = b"") -> Responder:
    return lambda received: Reply(status, body)


async def test_post_json_sends_payload_merges_headers_and_returns_decoded_body(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b'{"ok": true}'))
    http = HttpxHttpClient()

    body = await http.post_json(f"{server.url}/y", {"a": 1}, {"X-Key": "k"}, service="Svc")
    await http.aclose()

    (request,) = server.requests
    assert body == {"ok": True}
    assert request.method == "POST"
    assert request.path == "/y"
    assert request.json() == {"a": 1}
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-Key"] == "k"


async def test_post_json_raises_with_status_and_body_on_http_error(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.TOO_MANY_REQUESTS, b"slow down"))
    http = HttpxHttpClient()

    with pytest.raises(RuntimeError, match=r"Svc returned HTTP 429: slow down"):
        await http.post_json(server.url, {}, {}, service="Svc")
    await http.aclose()


async def test_post_json_tolerates_undecodable_error_bodies(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.INTERNAL_SERVER_ERROR, b"\xff\xfe"))
    http = HttpxHttpClient()

    with pytest.raises(RuntimeError, match="HTTP 500"):
        await http.post_json(server.url, {}, {}, service="Svc")
    await http.aclose()


async def test_post_json_names_the_service_and_url_when_unreachable(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    server.stop()
    http = HttpxHttpClient()

    with pytest.raises(RuntimeError, match=rf"Cannot reach Svc at {server.url}"):
        await http.post_json(server.url, {}, {}, service="Svc")
    await http.aclose()


async def test_post_json_rejects_a_non_json_success_body(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"<html>"))
    http = HttpxHttpClient()

    with pytest.raises(json.JSONDecodeError):
        await http.post_json(server.url, {}, {}, service="Svc")
    await http.aclose()


async def test_is_reachable_is_true_for_a_200_and_sends_the_headers(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    http = HttpxHttpClient()

    reachable = await http.is_reachable(f"{server.url}/ping", {"X-Key": "secret"})
    await http.aclose()

    (request,) = server.requests
    assert reachable is True
    assert request.method == "GET"
    assert request.headers["X-Key"] == "secret"


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.NO_CONTENT])
async def test_is_reachable_is_false_unless_the_server_answers_200(
    stub_server: StubFactory, status: HTTPStatus
) -> None:
    server = stub_server(_always(status))
    http = HttpxHttpClient()

    assert await http.is_reachable(server.url, {}) is False
    await http.aclose()


async def test_is_reachable_is_false_when_nothing_is_listening(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    server.stop()
    http = HttpxHttpClient()

    assert await http.is_reachable(server.url, {}) is False
    await http.aclose()


async def test_get_returns_the_body_and_content_type(stub_server: StubFactory) -> None:
    server = stub_server(lambda received: Reply(HTTPStatus.OK, b"jpeg bytes", "image/jpeg"))
    http = HttpxHttpClient()

    response = await http.get(f"{server.url}/images/a.jpg", {"X-Test": "1"}, "the API")
    await http.aclose()

    assert (response.body, response.content_type) == (b"jpeg bytes", "image/jpeg")
    assert server.requests[0].headers["X-Test"] == "1"


async def test_get_keeps_only_the_media_type_of_the_content_type(stub_server: StubFactory) -> None:
    server = stub_server(lambda received: Reply(HTTPStatus.OK, b"<p>", "Text/HTML; charset=utf-8"))
    http = HttpxHttpClient()

    response = await http.get(server.url, {}, "the API")
    await http.aclose()

    assert response.content_type == "text/html"


async def test_get_defaults_the_content_type_when_the_server_sends_none(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"bytes"))
    http = HttpxHttpClient()

    response = await http.get(server.url, {}, "the API")
    await http.aclose()

    assert response.content_type == "text/plain"


async def test_get_raises_the_status_and_body_on_http_error(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.NOT_FOUND, b"no such image"))
    http = HttpxHttpClient()

    with pytest.raises(HttpStatusError, match="the API returned HTTP 404: no such image") as caught:
        await http.get(f"{server.url}/images/a.jpg", {}, "the API")
    await http.aclose()

    assert caught.value.status == HTTPStatus.NOT_FOUND


async def test_get_names_the_service_and_url_when_unreachable(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK))
    url = server.url
    server.stop()
    http = HttpxHttpClient()

    with pytest.raises(RuntimeError, match="Cannot reach the API at"):
        await http.get(f"{url}/x", {}, "the API")
    await http.aclose()


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_is_reachable_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(HTTPStatus.MOVED_PERMANENTLY, headers={"Location": "/new"})
        return httpx.Response(HTTPStatus.OK)

    http = HttpxHttpClient(transport=_transport(handler))

    assert await http.is_reachable("http://svc/old", {}) is True
    await http.aclose()


async def test_the_client_is_created_by_the_first_call_and_shared_by_the_rest() -> None:
    seen: list[str] = []
    http = HttpxHttpClient(transport=_transport(lambda request: seen.append(request.url.path) or httpx.Response(200)))

    assert seen == []  # constructing it connected to nothing

    await http.get("http://svc/a", {}, "Svc")
    await http.get("http://svc/b", {}, "Svc")
    await http.aclose()

    assert seen == ["/a", "/b"]


async def test_closing_a_client_that_never_made_a_call_is_harmless() -> None:
    http = HttpxHttpClient()

    await http.aclose()
    await http.aclose()


async def test_a_closed_client_can_be_used_again() -> None:
    http = HttpxHttpClient(transport=_transport(lambda request: httpx.Response(HTTPStatus.OK, content=b"x")))
    await http.get("http://svc/a", {}, "Svc")
    await http.aclose()

    response = await http.get("http://svc/a", {}, "Svc")
    await http.aclose()

    assert response == HttpResponse(b"x", "text/plain")


def test_a_call_from_another_event_loop_fails_with_a_clear_error() -> None:
    http = HttpxHttpClient(transport=_transport(lambda request: httpx.Response(HTTPStatus.OK)))
    asyncio.run(http.get("http://svc/a", {}, "Svc"))  # its first call binds the client to this loop

    with pytest.raises(RuntimeError, match="bound to the event loop that made its first call"):
        asyncio.run(http.get("http://svc/a", {}, "Svc"))


def test_closing_from_another_event_loop_fails_with_a_clear_error() -> None:
    http = HttpxHttpClient(transport=_transport(lambda request: httpx.Response(HTTPStatus.OK)))
    asyncio.run(http.is_reachable("http://svc/a", {}))

    with pytest.raises(RuntimeError, match="bound to the event loop that made its first call"):
        asyncio.run(http.aclose())


def test_a_connection_limit_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_connections"):
        HttpxHttpClient(max_connections=0)
