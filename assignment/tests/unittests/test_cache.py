"""Unit tests for the cached_for decorator."""
from vlm_scene_description.bl.cache import cached_for


async def test_cache_hit_returns_same_result() -> None:
    calls = 0

    @cached_for(ttl=60.0)
    async def fn() -> int:
        nonlocal calls
        calls += 1
        return 42

    assert await fn() == 42
    assert await fn() == 42
    assert calls == 1  # second call served from cache


async def test_cache_different_args_have_separate_entries() -> None:
    @cached_for(ttl=60.0)
    async def double(x: int) -> int:
        return x * 2

    assert await double(1) == 2
    assert await double(2) == 4
    assert await double(1) == 2  # re-uses cached value for x=1


async def test_cache_kwargs_are_part_of_key() -> None:
    calls = 0

    @cached_for(ttl=60.0)
    async def fn(x: int = 0) -> int:
        nonlocal calls
        calls += 1
        return x

    await fn(x=1)
    await fn(x=2)
    await fn(x=1)  # cache hit for x=1

    assert calls == 2


async def test_cache_zero_ttl_never_caches() -> None:
    calls = 0

    @cached_for(ttl=0.0)
    async def fn() -> int:
        nonlocal calls
        calls += 1
        return 1

    await fn()
    await fn()

    assert calls == 2  # both calls hit the real function
