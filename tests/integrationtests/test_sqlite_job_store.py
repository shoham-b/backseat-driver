"""The monolith's job store over a real SQLite file: jobs must outlive the process that created them."""

from pathlib import Path
from uuid import uuid4

from backseat_driver.config import RunMode
from backseat_driver.jobs.factory import build_job_backend
from backseat_driver.jobs.sql_job_store import SqlJobStore
from backseat_driver.models import JobState, SceneDescription
from tests.fakes import FakeCaptioner, FakeImageStore, make_keyframe, make_settings


def _monolith_store(db_path: Path) -> SqlJobStore:
    settings = make_settings(mode=RunMode.MONOLITH, jobs_db_path=str(db_path))
    _, store = build_job_backend(settings, FakeCaptioner(), FakeImageStore())
    assert isinstance(store, SqlJobStore)
    return store


def test_jobs_and_descriptions_survive_a_restart(tmp_path: Path) -> None:
    database = tmp_path / "state" / "jobs.db"
    job_id, before = uuid4(), _monolith_store(database)
    before.create_job(job_id, 2, "tx-1")
    before.set_expected_scenes(job_id, 1)
    description = _describe(1)
    before.record_description(job_id, description)

    after = _monolith_store(database)  # a new process would build exactly this

    job = after.get_job(job_id)
    assert (job.state, job.completed_scenes, job.max_scenes) == (JobState.COMPLETED, 1, 2)
    assert [d.scene_name for d in after.list_descriptions(job_id)] == [description.scene_name]
    assert [j.job_id for j in after.list_jobs()] == [job_id]


def test_the_database_folder_is_created_when_missing(tmp_path: Path) -> None:
    database = tmp_path / "does" / "not" / "exist" / "jobs.db"

    _monolith_store(database)

    assert database.is_file()


def test_jobs_created_in_the_same_second_still_list_newest_first(tmp_path: Path) -> None:
    store = _monolith_store(tmp_path / "jobs.db")
    ids = [uuid4() for _ in range(5)]
    for job_id in ids:
        store.create_job(job_id, None, "tx")

    assert [job.job_id for job in store.list_jobs()] == ids[::-1]


def _describe(n: int) -> SceneDescription:
    keyframe = make_keyframe(n)
    return SceneDescription(
        scene_token=keyframe.scene_token,
        scene_name=keyframe.scene_name,
        camera_channel=keyframe.camera_channel,
        image_path=keyframe.image_path,
        description="a road",
        model_name="m",
    )
