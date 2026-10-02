"""Minimal JSON-over-HTTP helper shared by the network-backed caption backends."""

import json
import urllib.error
import urllib.request
from typing import Any


def post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float, service: str
) -> dict[str, Any]:
    """POST `payload` as JSON and return the decoded response, raising RuntimeError on any failure."""
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
