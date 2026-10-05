"""Behaviour every `JobStore` must have, run against each implementation.

The API and both workers are written against the port, and their tests use `FakeJobStore`; running the same cases
over the SQL store and that fake keeps the fake honest.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import pytest

from backseat_driver.errors import IdempotencyKeyInUseError, NotFoundError
from backseat_driver.models import DeadLetter, JobState, SceneDescription
from backseat_driver.transport.job_store.job_store import JobStore
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from backseat_driver.write.job_store.storage import JobStorage
from tests.fakes import FakeJobStore


@pytest.fixture(params=["sql", "fake"])
def store(request: pytest.FixtureRequest, sqlite_storage: JobStorage) -> JobStore:
    return SqlJobStore(sqlite_storage) if request.param == "sql" else FakeJobStore()


def _description(n: int, text: str | None = None, camera_channel: str = "CAM_FRONT") -> SceneDescription:
    return SceneDescription(
        scene_token=f"token-{n}",
        scene_name=f"scene-{n:04d}",
        camera_channel=camera_channel,
        image_path=f"samples/{camera_channel}/{n}.jpg",
        description=text or f"description {n}",
        model_name="fake-model",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _new_job(store: JobStore, expected_scenes: int | None = None, idempotency_key: str | None = None) -> UUID:
    job_id = uuid4()
    await store.create_job(job_id, None, "tx", idempotency_key)
    if expected_scenes is not None:
        await store.set_expected_scenes(job_id, expected_scenes)
    return job_id


async def test_a_new_job_is_pending_and_keeps_what_it_was_created_with(store: JobStore) -> None:
    job_id = uuid4()

    await store.create_job(job_id, 4, "tx-1")
    job = await store.get_job(job_id)

    assert job.state is JobState.PENDING
    assert (job.job_id, job.transaction_id, job.max_scenes) == (job_id, "tx-1", 4)
    assert (job.expected_scenes, job.completed_scenes, job.error) == (None, 0, None)


async def test_a_job_is_running_once_the_scene_count_is_known(store: JobStore) -> None:
    job_id = await _new_job(store)

    await store.set_expected_scenes(job_id, 2)

    assert (await store.get_job(job_id)).state is JobState.RUNNING


async def test_a_job_is_completed_when_every_expected_scene_is_recorded(store: JobStore) -> None:
    job_id = await _new_job(store, expected_scenes=2)
    await store.record_description(job_id, _description(1))

    await store.record_description(job_id, _description(2))
    job = await store.get_job(job_id)

    assert (job.state, job.completed_scenes) == (JobState.COMPLETED, 2)


async def test_a_job_with_no_scenes_is_completed_as_soon_as_that_is_known(store: JobStore) -> None:
    job_id = await _new_job(store)

    await store.set_expected_scenes(job_id, 0)

    assert (await store.get_job(job_id)).state is JobState.COMPLETED


async def test_a_redelivered_description_is_ignored_not_counted_or_overwritten(store: JobStore) -> None:
    job_id = await _new_job(store, expected_scenes=2)
    await store.record_description(job_id, _description(1))

    await store.record_description(job_id, _description(1, text="redelivery"))

    assert (await store.get_job(job_id)).completed_scenes == 1
    assert [d.description for d in await store.list_descriptions(job_id)] == ["description 1"]


async def test_descriptions_come_back_complete_and_sorted_by_scene_name(store: JobStore) -> None:
    job_id = await _new_job(store)
    labelled = _description(1).model_copy(update={"reference_description": "Parked truck"})
    await store.record_description(job_id, _description(2))
    await store.record_description(job_id, labelled)

    descriptions = await store.list_descriptions(job_id)

    assert [d.scene_name for d in descriptions] == ["scene-0001", "scene-0002"]
    # SQLite hands timestamps back without their timezone, which the Postgres column keeps.
    assert descriptions[0].model_dump(exclude={"generated_at"}) == labelled.model_dump(exclude={"generated_at"})


async def test_each_camera_of_a_scene_is_recorded_and_counted(store: JobStore) -> None:
    job_id = await _new_job(store, expected_scenes=2)

    await store.record_description(job_id, _description(1, camera_channel="CAM_FRONT"))
    await store.record_description(job_id, _description(1, camera_channel="CAM_BACK"))
    job = await store.get_job(job_id)

    assert (job.state, job.completed_scenes) == (JobState.COMPLETED, 2)


async def test_a_redelivered_camera_of_a_scene_is_ignored_next_to_its_other_cameras(store: JobStore) -> None:
    job_id = await _new_job(store, expected_scenes=3)
    await store.record_description(job_id, _description(1, camera_channel="CAM_FRONT"))
    await store.record_description(job_id, _description(1, camera_channel="CAM_BACK"))

    await store.record_description(job_id, _description(1, text="redelivery", camera_channel="CAM_BACK"))

    assert (await store.get_job(job_id)).completed_scenes == 2
    assert [d.description for d in await store.list_descriptions(job_id)] == ["description 1", "description 1"]


async def test_descriptions_are_sorted_by_scene_name_then_camera(store: JobStore) -> None:
    job_id = await _new_job(store)
    for n, camera_channel in [(2, "CAM_FRONT"), (1, "CAM_FRONT"), (1, "CAM_BACK")]:
        await store.record_description(job_id, _description(n, camera_channel=camera_channel))

    descriptions = await store.list_descriptions(job_id)

    assert [(d.scene_name, d.camera_channel) for d in descriptions] == [
        ("scene-0001", "CAM_BACK"),
        ("scene-0001", "CAM_FRONT"),
        ("scene-0002", "CAM_FRONT"),
    ]


async def test_a_job_without_descriptions_lists_none(store: JobStore) -> None:
    job_id = await _new_job(store)

    assert await store.list_descriptions(job_id) == []


async def test_descriptions_of_one_job_do_not_count_for_another(store: JobStore) -> None:
    first, second = await _new_job(store, expected_scenes=1), await _new_job(store, expected_scenes=1)

    await store.record_description(first, _description(1))

    assert (await store.get_job(first)).state is JobState.COMPLETED
    assert ((await store.get_job(second)).state, (await store.get_job(second)).completed_scenes) == (
        JobState.RUNNING,
        0,
    )


async def test_a_failed_job_keeps_its_progress(store: JobStore) -> None:
    job_id = await _new_job(store, expected_scenes=2)
    await store.record_description(job_id, _description(1))

    await store.fail_job(job_id, "boom")
    job = await store.get_job(job_id)

    assert (job.state, job.error, job.completed_scenes) == (JobState.FAILED, "boom", 1)


async def test_a_failed_job_keeps_the_first_error(store: JobStore) -> None:
    job_id = await _new_job(store)

    await store.fail_job(job_id, "first")
    await store.fail_job(job_id, "second")

    assert (await store.get_job(job_id)).error == "first"


async def test_a_job_is_found_by_its_idempotency_key(store: JobStore) -> None:
    job_id = await _new_job(store, idempotency_key="key-1")

    found = await store.find_job_by_idempotency_key("key-1")

    assert found is not None
    assert found.job_id == job_id


async def test_an_unknown_idempotency_key_finds_nothing(store: JobStore) -> None:
    await _new_job(store, idempotency_key="key-1")

    assert await store.find_job_by_idempotency_key("other") is None


async def test_a_second_job_cannot_claim_a_used_idempotency_key(store: JobStore) -> None:
    first = await _new_job(store, idempotency_key="key-1")

    with pytest.raises(IdempotencyKeyInUseError, match="key-1") as raised:
        await _new_job(store, idempotency_key="key-1")

    assert raised.value.key == "key-1"
    assert [job.job_id for job in await store.list_jobs()] == [first]


async def test_jobs_without_a_key_never_collide(store: JobStore) -> None:
    await _new_job(store)
    await _new_job(store)

    assert len(await store.list_jobs()) == 2


async def test_jobs_are_listed_newest_first_with_their_progress(store: JobStore) -> None:
    first = await _new_job(store)
    await asyncio.sleep(0.05)  # the Windows clock ticks every ~16 ms, so back-to-back jobs would tie on `created_at`
    second = await _new_job(store, expected_scenes=1)

    jobs = await store.list_jobs()

    assert [(job.job_id, job.state) for job in jobs] == [(second, JobState.RUNNING), (first, JobState.PENDING)]


async def test_a_store_without_jobs_lists_none(store: JobStore) -> None:
    assert await store.list_jobs() == []


async def _a_job_in_every_state(store: JobStore) -> dict[JobState, UUID]:
    jobs = {JobState.PENDING: await _new_job(store), JobState.RUNNING: await _new_job(store, expected_scenes=2)}
    jobs[JobState.COMPLETED] = await _new_job(store, expected_scenes=1)
    await store.record_description(jobs[JobState.COMPLETED], _description(1))
    jobs[JobState.FAILED] = await _new_job(store)
    await store.fail_job(jobs[JobState.FAILED], "boom")
    return jobs


@pytest.mark.parametrize("state", list(JobState))
async def test_listing_by_state_returns_exactly_the_jobs_in_that_state(store: JobStore, state: JobState) -> None:
    jobs = await _a_job_in_every_state(store)

    listed = await store.list_jobs(state=state)

    assert [(job.job_id, job.state) for job in listed] == [(jobs[state], state)]


async def test_the_limit_is_applied_after_the_state_filter(store: JobStore) -> None:
    pending = {await _new_job(store) for _ in range(3)}
    other = await _new_job(store, expected_scenes=1)

    listed = await store.list_jobs(state=JobState.PENDING, limit=2)

    assert len(listed) == 2
    assert {job.job_id for job in listed} <= pending
    assert other not in {job.job_id for job in listed}


async def test_a_limit_alone_caps_the_listing(store: JobStore) -> None:
    for _ in range(3):
        await _new_job(store)

    assert len(await store.list_jobs(limit=2)) == 2


def _dead_letter(task: Literal["ingest", "caption"] = "caption") -> DeadLetter:
    return DeadLetter(
        task=task,
        payload={"job_id": "j", "n": 1},
        error="ConnectionError: down",
        failed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_dead_letters_come_back_oldest_first_and_only_for_their_job(store: JobStore) -> None:
    job_id, other = await _new_job(store), await _new_job(store)

    await store.record_dead_letter(job_id, _dead_letter("ingest"))
    await store.record_dead_letter(job_id, _dead_letter("caption"))
    await store.record_dead_letter(other, _dead_letter("caption"))
    letters = await store.list_dead_letters(job_id)

    assert [letter.task for letter in letters] == ["ingest", "caption"]
    assert letters[0].model_dump(exclude={"failed_at"}) == _dead_letter("ingest").model_dump(exclude={"failed_at"})


async def test_recent_dead_letters_span_jobs_newest_first_up_to_the_limit(store: JobStore) -> None:
    first, second = await _new_job(store), await _new_job(store)
    await store.record_dead_letter(first, _dead_letter("ingest"))
    await store.record_dead_letter(second, _dead_letter("caption"))
    await store.record_dead_letter(first, _dead_letter("caption"))

    recent = await store.list_recent_dead_letters(limit=2)

    assert [(letter.job_id, letter.task) for letter in recent] == [(first, "caption"), (second, "caption")]


async def test_an_orphan_dead_letter_is_kept_without_a_job_and_listed_only_across_jobs(store: JobStore) -> None:
    job_id = await _new_job(store)

    await store.record_dead_letter(None, _dead_letter("ingest"))

    [orphan] = await store.list_recent_dead_letters(limit=10)
    assert (orphan.job_id, orphan.task) == (None, "ingest")
    assert await store.list_dead_letters(job_id) == []


async def test_a_store_without_dead_letters_lists_none(store: JobStore) -> None:
    assert await store.list_recent_dead_letters(limit=10) == []


async def test_a_dead_letter_does_not_change_the_job_state_by_itself(store: JobStore) -> None:
    job_id = await _new_job(store)

    await store.record_dead_letter(job_id, _dead_letter())

    assert (await store.get_job(job_id)).state is JobState.PENDING


@pytest.mark.parametrize(
    "operation",
    [
        lambda store, job_id: store.get_job(job_id),
        lambda store, job_id: store.set_expected_scenes(job_id, 3),
        lambda store, job_id: store.fail_job(job_id, "boom"),
        lambda store, job_id: store.list_descriptions(job_id),
        lambda store, job_id: store.record_description(job_id, _description(1)),
        lambda store, job_id: store.record_dead_letter(job_id, _dead_letter()),
        lambda store, job_id: store.list_dead_letters(job_id),
    ],
    ids=[
        "get_job",
        "set_expected_scenes",
        "fail_job",
        "list_descriptions",
        "record_description",
        "record_dead_letter",
        "list_dead_letters",
    ],
)
async def test_an_unknown_job_is_not_found(
    store: JobStore, operation: Callable[[JobStore, UUID], Awaitable[object]]
) -> None:
    unknown = uuid4()

    with pytest.raises(NotFoundError, match=str(unknown)):
        await operation(store, unknown)


async def test_the_store_reports_itself_healthy(store: JobStore) -> None:
    assert await store.healthcheck() is True
