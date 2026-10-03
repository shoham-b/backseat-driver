"""`UrllibHttpClient` against a real HTTP server on localhost, so no urllib internals need patching."""

import json
import threading
from collections.abc import Callable, Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from backseat_driver.captioning.http_client import UrllibHttpClient


class _Server:
    def __init__(self, status: HTTPStatus, body: bytes) -> None:
        self.requests: list[dict[str, Any]] = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": self.headers,
                        "body": self.rfile.read(length),
                    }
                )
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _answer

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self._open = True

    def stop(self) -> None:
        if self._open:
            self._open = False
            self.httpd.shutdown()
            self.httpd.server_close()


@pytest.fixture
def serve() -> Iterator[Callable[[HTTPStatus, bytes], _Server]]:
    servers: list[_Server] = []

    def start(status: HTTPStatus, body: bytes) -> _Server:
        servers.append(_Server(status, body))
        return servers[-1]

    yield start
    for server in servers:
        server.stop()


def test_post_json_sends_payload_merges_headers_and_returns_decoded_body(serve) -> None:
    server = serve(HTTPStatus.OK, b'{"ok": true}')

    body = UrllibHttpClient().post_json(f"{server.url}/y", {"a": 1}, {"X-Key": "k"}, timeout=7, service="Svc")

    (request,) = server.requests
    assert body == {"ok": True}
    assert request["method"] == "POST"
    assert request["path"] == "/y"
    assert json.loads(request["body"]) == {"a": 1}
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["X-Key"] == "k"


def test_post_json_raises_with_status_and_body_on_http_error(serve) -> None:
    server = serve(HTTPStatus.TOO_MANY_REQUESTS, b"slow down")

    with pytest.raises(RuntimeError, match=r"Svc returned HTTP 429: slow down"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_tolerates_undecodable_error_bodies(serve) -> None:
    server = serve(HTTPStatus.INTERNAL_SERVER_ERROR, b"\xff\xfe")

    with pytest.raises(RuntimeError, match="HTTP 500"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_names_the_service_and_url_when_unreachable(serve) -> None:
    server = serve(HTTPStatus.OK, b"{}")
    server.stop()

    with pytest.raises(RuntimeError, match=rf"Cannot reach Svc at {server.url}"):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_post_json_rejects_a_non_json_success_body(serve) -> None:
    server = serve(HTTPStatus.OK, b"<html>")

    with pytest.raises(json.JSONDecodeError):
        UrllibHttpClient().post_json(server.url, {}, {}, timeout=1, service="Svc")


def test_is_reachable_is_true_for_a_200_and_sends_the_headers(serve) -> None:
    server = serve(HTTPStatus.OK, b"{}")

    reachable = UrllibHttpClient().is_reachable(f"{server.url}/ping", {"X-Key": "secret"}, timeout=1)

    (request,) = server.requests
    assert reachable is True
    assert request["method"] == "GET"
    assert request["headers"]["X-Key"] == "secret"


@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.NO_CONTENT])
def test_is_reachable_is_false_unless_the_server_answers_200(serve, status: HTTPStatus) -> None:
    server = serve(status, b"")

    assert UrllibHttpClient().is_reachable(server.url, {}, timeout=1) is False


def test_is_reachable_is_false_when_nothing_is_listening(serve) -> None:
    server = serve(HTTPStatus.OK, b"{}")
    server.stop()

    assert UrllibHttpClient().is_reachable(server.url, {}, timeout=1) is False
