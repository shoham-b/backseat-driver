import _thread
import threading

import pytest

from backseat_driver.cli.interruptible import run_interruptibly


def test_returns_what_the_call_returns() -> None:
    result = run_interruptibly(lambda: 42)

    assert result == 42


def test_raises_what_the_call_raises() -> None:
    def fail() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_interruptibly(fail)


def test_an_interrupt_stops_the_wait_while_the_call_is_still_blocked() -> None:
    never = threading.Event()
    threading.Timer(0.2, _thread.interrupt_main).start()

    with pytest.raises(KeyboardInterrupt):
        run_interruptibly(lambda: never.wait(30))
