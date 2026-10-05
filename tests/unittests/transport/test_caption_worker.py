from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backseat_driver.errors import NotFoundError
from backseat_driver.models import CaptionTask, SceneDescription
from backseat_driver.transport.caption_worker import CaptionWorker
from tests.fakes import FakeCaptioner, FakeImageStore, FakeJobStore, make_image_uri, make_keyframe


def _caption_task(job_id: UUID, n: int = 1) -> CaptionTask:
    return CaptionTask(job_id=job_id, transaction_id="tx-1", keyframe=make_keyframe(n), image_uri=make_image_uri(n))


def _new_job(store: FakeJobStore, expected_scenes: int | None = None) -> UUID:
    job_id = uuid4()
    store.create_job(job_id, None, "tx-1")
    if expected_scenes is not None:
        store.set_expected_scenes(job_id, expected_scenes)
    return job_id


class _FailingCaptioner(FakeCaptioner):
    async def caption(self, image_path: str) -> str:
        raise RuntimeError("model exploded")


class _StoreThatIsDown(FakeJobStore):
    def record_description(self, job_id: UUID, description: SceneDescription) -> None:
        raise ConnectionError("db down")


def test_caption_records_the_caption_under_the_model_that_wrote_it() -> None:
    store = FakeJobStore()
    job_id = _new_job(store)

    CaptionWorker(FakeCaptioner("dusk"), store, FakeImageStore()).handle(_caption_task(job_id))
    [description] = store.list_descriptions(job_id)

    assert (description.description, description.model_name) == ("dusk", "fake-model")


def test_caption_records_the_keyframe_fields_and_a_fresh_timestamp() -> None:
    store = FakeJobStore()
    job_id = _new_job(store)
    keyframe = make_keyframe(7)
    before = datetime.now(UTC)

    CaptionWorker(FakeCaptioner(), store, FakeImageStore()).handle(_caption_task(job_id, 7))
    [description] = store.list_descriptions(job_id)

    assert (description.scene_token, description.scene_name, description.image_path) == (
        keyframe.scene_token,
        keyframe.scene_name,
        keyframe.image_path,
    )
    assert description.generated_at >= before


def test_caption_reads_the_local_copy_but_records_the_dataset_path() -> None:
    store, captioner = FakeJobStore(), FakeCaptioner()
    job_id = _new_job(store)

    CaptionWorker(captioner, store, FakeImageStore()).handle(_caption_task(job_id))
    [description] = store.list_descriptions(job_id)

    assert captioner.seen_paths == [str(Path("/fetched/1.jpg"))]
    assert description.image_path == "/img/1.jpg"


def test_caption_redelivery_is_idempotent() -> None:
    store = FakeJobStore()
    job_id = _new_job(store, expected_scenes=1)
    worker = CaptionWorker(FakeCaptioner(), store, FakeImageStore())

    worker.handle(_caption_task(job_id))
    worker.handle(_caption_task(job_id))

    assert store.get_job(job_id).completed_scenes == 1
    assert len(store.list_descriptions(job_id)) == 1


def test_caption_failure_propagates_and_records_nothing() -> None:
    store = FakeJobStore()
    job_id = _new_job(store)

    with pytest.raises(RuntimeError, match="model exploded"):
        CaptionWorker(_FailingCaptioner(), store, FakeImageStore()).handle(_caption_task(job_id))

    assert store.list_descriptions(job_id) == []


def test_caption_releases_the_local_copy_even_when_captioning_fails() -> None:
    store, images = FakeJobStore(), FakeImageStore()
    job_id = _new_job(store)

    with pytest.raises(RuntimeError):
        CaptionWorker(_FailingCaptioner(), store, images).handle(_caption_task(job_id))

    assert images.released == images.opened == [make_image_uri(1)]


def test_caption_store_failure_propagates_so_the_message_is_not_acked() -> None:
    worker = CaptionWorker(FakeCaptioner(), _StoreThatIsDown(), FakeImageStore())

    with pytest.raises(ConnectionError):
        worker.handle(_caption_task(uuid4()))


def test_caption_for_an_unknown_job_raises() -> None:
    worker = CaptionWorker(FakeCaptioner(), FakeJobStore(), FakeImageStore())

    with pytest.raises(NotFoundError):
        worker.handle(_caption_task(uuid4()))
