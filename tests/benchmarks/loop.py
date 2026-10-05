"""One event loop shared by the benchmarks.

A real run starts a single loop and awaits everything on it, so a benchmark that started a loop per iteration
(`asyncio.run`) would mostly time loop setup, which the code under test never pays per call.
"""

import asyncio
import atexit
from collections.abc import Coroutine
from typing import Any

_LOOP = asyncio.new_event_loop()
atexit.register(_LOOP.close)


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return _LOOP.run_until_complete(coroutine)
