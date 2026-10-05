"""Run a blocking call so that Ctrl-C can stop it.

On Windows a Python signal handler only runs once the main thread is back in bytecode, so Ctrl-C is ignored for as
long as a socket read, a model forward pass or a download chunk is blocked, which can be minutes. The call therefore
runs on a daemon thread while the main thread waits in short slices, where the interrupt is delivered at once.
"""

import threading
from collections.abc import Callable
from concurrent.futures import Future, wait

_POLL_SECONDS = 0.1


def run_interruptibly[T](call: Callable[[], T]) -> T:
    """Return what `call` returns or raise what it raises; KeyboardInterrupt abandons it (the thread dies with us)."""
    outcome: Future[T] = Future()

    def target() -> None:
        try:
            outcome.set_result(call())
        except BaseException as exc:  # re-raised in the caller by `outcome.result()`, not swallowed
            outcome.set_exception(exc)

    threading.Thread(target=target, daemon=True).start()
    while not outcome.done():
        wait([outcome], _POLL_SECONDS)
    return outcome.result()
