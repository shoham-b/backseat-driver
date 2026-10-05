import asyncio
import threading

import pytest

from backseat_driver.transport.worker_loop import WorkerLoop


async def _running_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def test_run_returns_what_the_coroutine_returns() -> None:
    loop = WorkerLoop()

    async def answer() -> int:
        return 42

    result = loop.run(answer())
    loop.close()

    assert result == 42


def test_every_run_uses_the_same_loop() -> None:
    loop = WorkerLoop()

    first = loop.run(_running_loop())
    second = loop.run(_running_loop())
    loop.close()

    assert first is second


def test_work_started_in_one_run_can_finish_in_a_later_one() -> None:
    loop, release = WorkerLoop(), asyncio.Event()

    async def start() -> asyncio.Task[str]:
        async def wait() -> str:
            await release.wait()
            return "finished"

        return asyncio.create_task(wait())

    async def finish(task: asyncio.Task[str]) -> str:
        release.set()
        return await task

    task = loop.run(start())
    result = loop.run(finish(task))
    loop.close()

    assert result == "finished"


def test_a_failing_coroutine_raises_and_leaves_the_loop_usable() -> None:
    loop = WorkerLoop()

    async def fail() -> None:
        raise RuntimeError("boom")

    before = loop.run(_running_loop())

    with pytest.raises(RuntimeError, match="boom"):
        loop.run(fail())
    after = loop.run(_running_loop())
    still_open = not after.is_closed()
    loop.close()

    assert after is before
    assert still_open


def test_threads_calling_run_at_once_take_turns_instead_of_failing() -> None:
    loop = WorkerLoop()
    running = overlap = 0
    results: list[int] = []

    async def work(n: int) -> int:
        nonlocal running, overlap
        running += 1
        overlap = max(overlap, running)
        await asyncio.sleep(0.01)
        running -= 1
        return n

    threads = [threading.Thread(target=lambda n=n: results.append(loop.run(work(n)))) for n in range(5)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    loop.close()

    assert sorted(results) == [0, 1, 2, 3, 4]
    assert overlap == 1


def test_a_forked_process_gets_its_own_loop_and_never_closes_its_parents() -> None:
    pid = 100
    loop = WorkerLoop(current_pid=lambda: pid)
    parents = loop.run(_running_loop())

    pid = 200  # as in a forked child that inherited `loop`
    childs = loop.run(_running_loop())
    loop.close()

    assert childs is not parents
    assert childs.is_closed()
    assert not parents.is_closed()
    parents.close()


def test_closing_twice_is_harmless_and_a_closed_loop_is_replaced_on_next_use() -> None:
    loop = WorkerLoop()
    first = loop.run(_running_loop())

    loop.close()
    loop.close()
    second = loop.run(_running_loop())
    loop.close()

    assert first.is_closed()
    assert second is not first
