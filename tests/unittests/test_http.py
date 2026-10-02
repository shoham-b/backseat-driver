import io
import json
import urllib.error
import urllib.request
from email.message import Message
from http import HTTPStatus
from typing import Any

import pytest

from backseat_driver.adapters._http import post_json


class _Response(io.BytesIO):
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:  # ty: ignore[invalid-method-override]
        self.close()


def test_post_json_sends_payload_merges_headers_and_returns_decoded_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)  # ty: ignore[invalid-argument-type]
        seen["headers"] = dict(request.header_items())
        seen["timeout"] = timeout
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    body = post_json("http://x/y", {"a": 1}, {"X-Key": "k"}, timeout=7, service="Svc")

    assert body == {"ok": True}
    assert seen["url"] == "http://x/y"
    assert seen["body"] == {"a": 1}
    assert seen["headers"]["Content-type"] == "application/json"
    assert seen["headers"]["X-key"] == "k"
    assert seen["timeout"] == 7


def test_post_json_raises_with_status_and_body_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        raise urllib.error.HTTPError(
            request.full_url, HTTPStatus.TOO_MANY_REQUESTS, "Too Many", Message(), io.BytesIO(b"slow down")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=r"Svc returned HTTP 429: slow down"):
        post_json("http://x", {}, {}, timeout=1, service="Svc")


def test_post_json_tolerates_undecodable_error_bodies(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        raise urllib.error.HTTPError(
            request.full_url, HTTPStatus.INTERNAL_SERVER_ERROR, "boom", Message(), io.BytesIO(b"\xff\xfe")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        post_json("http://x", {}, {}, timeout=1, service="Svc")


def test_post_json_names_the_service_and_url_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match=r"Cannot reach Svc at http://x: refused"):
        post_json("http://x", {}, {}, timeout=1, service="Svc")


def test_post_json_rejects_a_non_json_success_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: _Response(b"<html>"))

    with pytest.raises(json.JSONDecodeError):
        post_json("http://x", {}, {}, timeout=1, service="Svc")
