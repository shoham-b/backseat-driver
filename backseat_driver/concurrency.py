"""Running many awaitables at once, with a cap, and with a failure stopping the rest."""

import asyncio
from collections.abc import Awaitable, Iterable


async def gather_all[T](awaitables: Iterable[Awaitable[T]], limit: int | None = None) -> list[T]:
    """Await all of `awaitables`, at most `limit` at a time (all at once when None), and return their results in input
    order.

    Unlike `asyncio.gather`, the first failure cancels the ones still running instead of leaving them to finish (and
    bill, or hold a file) with nobody listening, and it is raised as itself, not as a `TaskGroup`'s `ExceptionGroup`,
    so callers keep catching the domain error they always did.
    """
    if limit is not None and limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    slots = None if limit is None else asyncio.Semaphore(limit)

    async def run(awaitable: Awaitable[T]) -> T:
        if slots is None:
            return await awaitable
        async with slots:
            return await awaitable

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(run(awaitable)) for awaitable in awaitables]
    except BaseExceptionGroup as failures:
        raise failures.exceptions[0] from None
    return [task.result() for task in tasks]
