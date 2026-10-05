"""The event loop a Celery worker process keeps for its whole life.

A Celery task is a plain function, so it cannot be `async def`; it hands its coroutine to this loop instead of
starting one per task. One loop that outlives the tasks is what lets the process keep pooled database connections and
reuse clients: an async resource belongs to the loop that created it, and a loop started per task would orphan it.

The loop is created on first use, so a worker process that forks gets its own, never its parent's.
"""

import asyncio
import atexit
import os
from collections.abc import Callable, Coroutine
from typing import Any


class WorkerLoop:
    def __init__(self, current_pid: Callable[[], int] = os.getpid) -> None:
        self._current_pid = current_pid
        self._loop: asyncio.AbstractEventLoop | None = None
        self._owner_pid: int | None = None

    def run[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        """Run `coroutine` to completion on this process's loop. Raises what it raises; the loop stays usable."""
        return self._get().run_until_complete(coroutine)

    def close(self) -> None:
        """Finish the loop's async generators and executor, then close it. Safe to call again."""
        loop, self._loop = self._loop, None
        if loop is None or self._owner_pid != self._current_pid() or loop.is_closed():
            return  # a forked child never closes the loop it inherited: it is the parent's
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()

    def _get(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._owner_pid != self._current_pid():
            self._loop = asyncio.new_event_loop()
            self._owner_pid = self._current_pid()
        return self._loop


worker_loop = WorkerLoop()
atexit.register(worker_loop.close)
