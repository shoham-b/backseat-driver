"""Caching utilities for the business-logic layer."""
import time
from collections.abc import Callable
from functools import wraps
from typing import Any


def cached_for(ttl: float) -> Callable[..., Any]:
    """Cache async function results for *ttl* seconds.

    Uses the full call signature (positional args + keyword args) as the cache
    key. Not thread-safe — suitable for single-process async workloads.

    Usage::

        @cached_for(ttl=60.0)
        async def fetch_exchange_rates() -> dict[str, float]:
            return await external_api.get_rates()
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _cache: dict[tuple[Any, ...], tuple[Any, float]] = {}

        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            if key in _cache:
                value, expires_at = _cache[key]
                if time.monotonic() < expires_at:
                    return value
            value = await fn(*args, **kwargs)
            _cache[key] = (value, time.monotonic() + ttl)
            return value

        return wrapper

    return decorator
