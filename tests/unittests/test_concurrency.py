import asyncio

import pytest

from backseat_driver.concurrency import gather_all


async def test_results_come_back_in_input_order_whatever_the_finishing_order() -> None:
    async def after(delay: float, value: str) -> str:
        await asyncio.sleep(delay)
        return value

    results = await gather_all([after(0.02, "a"), after(0.0, "b"), after(0.01, "c")])

    assert results == ["a", "b", "c"]


async def test_everything_runs_at_once() -> None:
    running = peak = 0

    async def work() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    await gather_all(work() for _ in range(10))

    assert peak == 10


async def test_the_first_failure_is_raised_as_itself_and_cancels_the_rest() -> None:
    cancelled = asyncio.Event()

    async def slow() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def fail() -> None:
        await asyncio.sleep(0)
        raise KeyError("boom")

    with pytest.raises(KeyError, match="boom"):
        await gather_all([slow(), fail()])

    assert cancelled.is_set()


async def test_nothing_to_run_returns_an_empty_list() -> None:
    assert await gather_all([]) == []
