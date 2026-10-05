"""A real HTTP server on localhost for tests that need to talk to one, so no HTTP library has to be patched.

Each test supplies a function from the request to the reply; the server records every request it served.
"""

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import Message
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class Received:
    method: str
    path: str
    headers: "Message[str, str]"  # generic only for the type checker
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass(frozen=True)
class Reply:
    status: HTTPStatus = HTTPStatus.OK
    body: bytes = b""
    content_type: str | None = None


def json_reply(value: object, status: HTTPStatus = HTTPStatus.OK) -> Reply:
    return Reply(status, json.dumps(value).encode(), "application/json")


Responder = Callable[[Received], Reply]


@dataclass
class StubServer:
    respond: Responder
    requests: list[Received] = field(default_factory=list)
    _stopped: bool = False

    def __post_init__(self) -> None:
        server = self
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                received = Received(self.command, self.path, self.headers, self.rfile.read(length))
                requests.append(received)
                reply = server.respond(received)
                self.send_response(reply.status)
                if reply.content_type:
                    self.send_header("Content-Type", reply.content_type)
                self.send_header("Content-Length", str(len(reply.body)))
                self.end_headers()
                self.wfile.write(reply.body)

            do_GET = do_POST = _answer

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        """Safe to call twice, so a test can stop the server to see how its client copes with nothing listening."""
        if not self._stopped:
            self._stopped = True
            self._httpd.shutdown()
            self._httpd.server_close()
