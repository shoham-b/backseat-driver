"""Stands in for an Ollama server in the CI cluster: answers every caption after a fixed delay.

The delay keeps captions in flight long enough for the queue to back up, which is what the autoscaling test needs.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAPTION_SECONDS = 2


class Handler(BaseHTTPRequestHandler):
    def _reply(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._reply({"models": []})

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(CAPTION_SECONDS)
        self._reply({"response": "a stub caption"})

    def log_message(self, *args: object) -> None:
        pass


ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
