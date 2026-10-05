"""Polling for work that finishes elsewhere (another thread, or another task on the loop), with one place that owns
the timeout."""

import asyncio
import time
from collections.abc import Awaitable, Callable


def wait_until(condition: Callable[[], bool], what: str, timeout: float = 10.0, interval: float = 0.01) -> None:
    """Block until `condition()` holds, failing with `what` if it never does within `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out after {timeout}s waiting for {what}")
        time.sleep(interval)


ASYNC_TIMEOUT_SECONDS = 10.0


async def wait_until_async(condition: Callable[[], Awaitable[bool]], what: str, interval: float = 0.01) -> None:
    """`wait_until` for a condition that is awaited, yielding to the loop between checks."""
    try:
        async with asyncio.timeout(ASYNC_TIMEOUT_SECONDS):
            # Polling on purpose: the condition is state in a store, and nothing signals when it changes.
            while not await condition():  # noqa: ASYNC110
                await asyncio.sleep(interval)
    except TimeoutError:
        raise AssertionError(f"timed out after {ASYNC_TIMEOUT_SECONDS}s waiting for {what}") from None
