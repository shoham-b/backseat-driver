from pathlib import Path

import pytest

from backseat_driver.config import RunMode
from backseat_driver.pipeline import ScenePipeline
from backseat_driver.read.images.local_image_store import LocalImageStore
from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore
from backseat_driver.stacks import build_image_store, build_job_backend, machines, pipeline
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from backseat_driver.write.job_store.in_memory_job_store import InMemoryJobStore
from backseat_driver.write.job_store.sql_job_store import SqlJobStore
from tests.fakes import FakeCaptioner, FakeImageStore, make_settings

DISTRIBUTED = {"mode": RunMode.DISTRIBUTED, "dataset_bucket": "bucket"}


def test_rung_1_builds_a_pipeline_without_a_queue_or_a_store() -> None:
    settings = make_settings()

    built = pipeline(settings, dataroot="data", version="v1.0-mini", cameras=["CAM_FRONT"])

    assert isinstance(built, ScenePipeline)


def test_the_monolith_reads_images_from_the_local_dataroot() -> None:
    assert isinstance(build_image_store(make_settings()), LocalImageStore)


def test_distributed_reads_images_from_the_bucket() -> None:
    assert isinstance(build_image_store(make_settings(**DISTRIBUTED)), S3DatasetStore)


def test_rung_2_hands_off_in_process_and_keeps_jobs_in_memory_without_a_database_path() -> None:
    queue, store = build_job_backend(make_settings(), FakeCaptioner(), FakeImageStore())

    assert isinstance(queue, InProcessJobQueue)
    assert isinstance(store, InMemoryJobStore)


def test_rung_2_keeps_jobs_in_a_sqlite_file_when_given_a_path(tmp_path: Path) -> None:
    settings = make_settings(jobs_db_path=str(tmp_path / "jobs.db"))

    _, store = build_job_backend(settings, FakeCaptioner(), FakeImageStore())

    assert isinstance(store, SqlJobStore)


@pytest.mark.parametrize("build", [machines, lambda s: build_job_backend(s, FakeCaptioner(), FakeImageStore())])
def test_rung_3_hands_off_over_rabbitmq_into_the_shared_database(build) -> None:
    queue, store = build(make_settings(**DISTRIBUTED))

    assert isinstance(queue, CeleryJobQueue)
    assert isinstance(store, SqlJobStore)
