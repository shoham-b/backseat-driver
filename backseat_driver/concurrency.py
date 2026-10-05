"""Running many coroutines at once, with a failure stopping the rest."""

import asyncio
from collections.abc import Coroutine, Iterable
from typing import Any


async def gather_all[T](coroutines: Iterable[Coroutine[Any, Any, T]]) -> list[T]:
    """Await all of `coroutines` at once and return their results in input order.

    Unlike `asyncio.gather`, the first failure cancels the ones still running instead of leaving them to finish (and
    bill) with nobody listening, and it is raised as itself, not as a `TaskGroup`'s `ExceptionGroup`, so callers keep
    catching the domain error they always did.
    """
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(coroutine) for coroutine in coroutines]
    except BaseExceptionGroup as failures:
        raise failures.exceptions[0] from None
    return [task.result() for task in tasks]
