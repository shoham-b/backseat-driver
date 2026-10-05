"""`UrllibHttpClient` against a real HTTP server on localhost, so no urllib internals need patching."""

import json
from collections.abc import Callable
from http import HTTPStatus

import pytest

from backseat_driver.process.http_client import UrllibHttpClient
from tests.stub_server import Reply, Responder, StubServer

StubFactory = Callable[[Responder], StubServer]


def _always(status: HTTPStatus, body: bytes = b"") -> Responder:
    return lambda received: Reply(status, body)


def test_post_json_sends_payload_merges_headers_and_returns_decoded_body(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b'{"ok": true}'))

    body = UrllibHttpClient().post_json(f"{server.url}/y", {"a": 1}, {"X-Key": "k"}, timeout=7, service="Svc")

    (request,) = server.requests
    assert body == {"ok": True}
    assert request.method == "POST"
    assert request.path == "/y"
    assert request.json() == {"a": 1}
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["X-Key"] == "k"


def test_post_json_raises_with_status_and_body_on_http_error(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.TOO_MANY_REQUESTS, b"slow down"))

    with pytest.raises(RuntimeError, match=r"Svc returned HTTP 429: slow down"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_tolerates_undecodable_error_bodies(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.INTERNAL_SERVER_ERROR, b"\xff\xfe"))

    with pytest.raises(RuntimeError, match="HTTP 500"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_names_the_service_and_url_when_unreachable(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    server.stop()

    with pytest.raises(RuntimeError, match=rf"Cannot reach Svc at {server.url}"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_rejects_a_non_json_success_body(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"<html>"))

    with pytest.raises(json.JSONDecodeError):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_is_reachable_is_true_for_a_200_and_sends_the_headers(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))

    reachable = UrllibHttpClient().is_reachable(f"{server.url}/ping", {"X-Key": "secret"}, timeout=1)

    (request,) = server.requests
    assert reachable is True
    assert request.method == "GET"
    assert request.headers["X-Key"] == "secret"


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.NO_CONTENT])
def test_is_reachable_is_false_unless_the_server_answers_200(stub_server: StubFactory, status: HTTPStatus) -> None:
    server = stub_server(_always(status))

    assert UrllibHttpClient().is_reachable(server.url, {}, timeout=1) is False


def test_is_reachable_is_false_when_nothing_is_listening(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"{}"))
    server.stop()

    assert UrllibHttpClient().is_reachable(server.url, {}, timeout=1) is False


def test_get_returns_the_body_and_content_type(stub_server: StubFactory) -> None:
    server = stub_server(lambda received: Reply(HTTPStatus.OK, b"jpeg bytes", "image/jpeg"))

    response = UrllibHttpClient().get(f"{server.url}/images/a.jpg", {"X-Test": "1"}, 5, "the API")

    assert (response.body, response.content_type) == (b"jpeg bytes", "image/jpeg")
    assert server.requests[0].headers["X-Test"] == "1"


def test_get_defaults_the_content_type_when_the_server_sends_none(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK, b"bytes"))

    response = UrllibHttpClient().get(server.url, {}, 5, "the API")

    assert response.content_type == "text/plain"  # urllib's default for a reply without a Content-Type


def test_get_raises_with_status_and_body_on_http_error(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.NOT_FOUND, b"no such image"))

    with pytest.raises(RuntimeError, match="the API returned HTTP 404: no such image"):
        UrllibHttpClient().get(f"{server.url}/images/a.jpg", {}, 5, "the API")


def test_get_names_the_service_and_url_when_unreachable(stub_server: StubFactory) -> None:
    server = stub_server(_always(HTTPStatus.OK))
    url = server.url
    server.stop()

    with pytest.raises(RuntimeError, match="Cannot reach the API at"):
        UrllibHttpClient().get(f"{url}/x", {}, 1, "the API")
