"""Polling for work that finishes on another thread, with one place that owns the timeout."""

import time
from collections.abc import Callable


def wait_until(condition: Callable[[], bool], what: str, timeout: float = 10.0, interval: float = 0.01) -> None:
    """Block until `condition()` holds, failing with `what` if it never does within `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out after {timeout}s waiting for {what}")
        time.sleep(interval)
