"""`HttpxAsyncHttpClient` against a real HTTP server on localhost, with the same cases as the urllib client."""

from collections.abc import Callable
from http import HTTPStatus

import pytest

from backseat_driver.process.async_http_client import HttpxAsyncHttpClient
from tests.stub_server import Reply, Responder, StubServer

StubFactory = Callable[[Responder], StubServer]


def _always(status: HTTPStatus, body: bytes = b"") -> Responder:
    return lambda received: Reply(status, body)


async def test_post_json_sends_payload_merges_headers_and_returns_decoded_body(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b'{"ok": true}'))

    body = await HttpxAsyncHttpClient().post_json(f"{server.url}/y", {"a": 1}, {"X-Key": "k"}, service="Svc")

    (request,) = server.requests
    assert body == {"ok": True}
    assert request.method == "POST"
    assert request.path == "/y"
    assert request.json() == {"a": 1}
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-Key"] == "k"


async def test_post_json_raises_with_status_and_body_on_http_error(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.TOO_MANY_REQUESTS, b"slow down"))

    with pytest.raises(RuntimeError, match=r"Svc returned HTTP 429: slow down"):
        await HttpxAsyncHttpClient().post_json(server.url, {}, {}, service="Svc")


async def test_post_json_tolerates_undecodable_error_bodies(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.INTERNAL_SERVER_ERROR, b"\xff\xfe"))

    with pytest.raises(RuntimeError, match="HTTP 500"):
        await HttpxAsyncHttpClient().post_json(server.url, {}, {}, service="Svc")


async def test_post_json_names_the_service_and_url_when_unreachable(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    server.stop()

    with pytest.raises(RuntimeError, match=rf"Cannot reach Svc at {server.url}"):
        await HttpxAsyncHttpClient().post_json(server.url, {}, {}, service="Svc")
