"""Run a blocking call so that Ctrl-C can stop it.

On Windows a Python signal handler only runs once the main thread is back in bytecode, so Ctrl-C is ignored for as
long as a socket read, a model forward pass or a download chunk is blocked, which can be minutes. The call therefore
runs on a daemon thread while the main thread waits in short slices, where the interrupt is delivered at once.
"""

import threading
from collections.abc import Callable

_POLL_SECONDS = 0.1


def run_interruptibly[T](call: Callable[[], T]) -> T:
    """Return what `call` returns or raise what it raises; KeyboardInterrupt abandons it (the thread dies with us)."""
    outcome: list[T] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            outcome.append(call())
        except BaseException as exc:  # re-raised in the caller, not swallowed
            failure.append(exc)

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(_POLL_SECONDS)
    if failure:
        raise failure[0]
    return outcome[0]
