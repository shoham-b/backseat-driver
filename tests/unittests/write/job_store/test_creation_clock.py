from datetime import UTC, datetime, timedelta
from itertools import pairwise
from threading import Thread
from uuid import uuid4

from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backseat_driver.transport.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.creation_clock import CreationClock
from backseat_driver.write.job_store.storage import JobStorage

NOON = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _frozen() -> CreationClock:
    """A clock whose wall clock never moves, like two readings inside one 15 ms tick."""
    return CreationClock(now=lambda: NOON)


def test_a_reading_later_than_the_last_is_returned_as_it_is() -> None:
    readings = iter([NOON, NOON + timedelta(seconds=5)])
    clock = CreationClock(now=lambda: next(readings))

    first, second = clock(), clock()

    assert (first, second) == (NOON, NOON + timedelta(seconds=5))


def test_a_clock_that_stands_still_still_hands_out_later_values() -> None:
    clock = _frozen()

    values = [clock() for _ in range(3)]

    assert values == [NOON, NOON + timedelta(microseconds=1), NOON + timedelta(microseconds=2)]


def test_a_clock_that_steps_backwards_never_hands_out_an_earlier_value() -> None:
    readings = iter([NOON, NOON - timedelta(seconds=30)])
    clock = CreationClock(now=lambda: next(readings))

    first, second = clock(), clock()

    assert second > first


@given(st.lists(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1)), min_size=1, max_size=40))
def test_values_strictly_increase_whatever_the_wall_clock_does(readings: list[datetime]) -> None:
    feed = iter(readings)
    clock = CreationClock(now=lambda: next(feed))

    values = [clock() for _ in readings]

    assert all(later > earlier for earlier, later in pairwise(values))
    assert all(value >= reading for value, reading in zip(values, readings, strict=True))


def test_threads_sharing_a_clock_never_get_the_same_value() -> None:
    clock = _frozen()
    values: list[datetime] = []

    def draw() -> None:
        values.extend(clock() for _ in range(200))

    threads = [Thread(target=draw) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(values)) == 8 * 200


def test_the_in_memory_store_lists_jobs_created_within_one_tick_newest_first() -> None:
    store, ids = InMemoryJobStore(clock=_frozen()), [uuid4() for _ in range(5)]
    for job_id in ids:
        store.create_job(job_id, None, "tx")

    listed = store.list_jobs()

    assert [job.job_id for job in listed] == ids[::-1]


def test_the_sql_store_lists_jobs_created_within_one_tick_newest_first() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    storage = JobStorage("sqlite://", engine_factory=lambda *_, **__: engine, clock=_frozen())
    storage.ensure_schema()
    store, ids = SqlJobStore(storage), [uuid4() for _ in range(5)]
    for job_id in ids:
        store.create_job(job_id, None, "tx")

    listed = store.list_jobs()

    assert [job.job_id for job in listed] == ids[::-1]
