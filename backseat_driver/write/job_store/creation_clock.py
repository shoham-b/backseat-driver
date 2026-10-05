"""Timestamps that put jobs in creation order even where the wall clock ticks coarsely."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import Lock


def utc_now() -> datetime:
    return datetime.now(UTC)


class CreationClock:
    """Hands out `created_at` values, each strictly later than the one before.

    The wall clock ticks coarsely on some platforms (about 15 ms on Windows) and can step backwards, so jobs created in
    a row would share a `created_at` and a newest-first listing could not tell them apart. The order holds within the
    process that owns the clock; two replicas creating a job in the same microsecond can still tie.
    """

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._last: datetime | None = None
        self._lock = Lock()

    def __call__(self) -> datetime:
        with self._lock:
            reading = self._now()
            if self._last is not None and reading <= self._last:
                reading = self._last + timedelta(microseconds=1)
            self._last = reading
            return reading
