from datetime import UTC, datetime
from unittest import mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from backseat_driver.db import storage
from backseat_driver.db.orm import SceneDescriptionRow
from backseat_driver.db.storage import JobStorage


def _values(n: int = 1) -> dict:
    return {
        "scene_token": f"token-{n}",
        "scene_name": f"scene-{n:04d}",
        "camera_channel": "CAM_FRONT",
        "image_path": f"/img/{n}.jpg",
        "description": f"description {n}",
        "model_name": "fake-model",
        "generated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }


def test_constructing_storage_never_creates_an_engine() -> None:
    with mock.patch.object(storage, "create_engine") as create_engine:
        JobStorage("postgresql+psycopg://host/db")

    create_engine.assert_not_called()


def test_engine_is_created_once_with_bounded_pool_and_fast_connect_timeout() -> None:
    with mock.patch.object(storage, "create_engine") as create_engine:
        job_storage = JobStorage("postgresql+psycopg://host/db")

        job_storage.ping()
        job_storage.ping()

    create_engine.assert_called_once_with(
        "postgresql+psycopg://host/db",
        pool_size=4,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def test_ping_is_false_and_does_not_raise_when_database_is_unreachable() -> None:
    with mock.patch.object(storage, "create_engine") as create_engine:
        create_engine.return_value.connect.side_effect = OperationalError("SELECT 1", {}, Exception("refused"))

        reachable = JobStorage("postgresql+psycopg://host/db").ping()

    assert reachable is False


def test_ping_is_true_when_database_answers(sqlite_storage: JobStorage) -> None:
    assert sqlite_storage.ping() is True


def test_ping_propagates_unexpected_errors() -> None:
    with mock.patch.object(storage, "create_engine") as create_engine:
        create_engine.return_value.connect.side_effect = RuntimeError("not a database error")

        with pytest.raises(RuntimeError, match="not a database error"):
            JobStorage("postgresql+psycopg://host/db").ping()


def test_fetch_unknown_job_is_none(sqlite_storage: JobStorage) -> None:
    assert sqlite_storage.fetch_job(uuid4()) is None


def test_inserted_job_is_fetched_with_zero_completed_scenes(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()

    sqlite_storage.insert_job(job_id, max_scenes=5, transaction_id="tx-1")
    found = sqlite_storage.fetch_job(job_id)

    assert found is not None
    row, completed = found
    assert (row.job_id, row.max_scenes, row.transaction_id, row.expected_scenes) == (job_id, 5, "tx-1", None)
    assert row.created_at is not None
    assert completed == 0


def test_job_without_a_scene_limit_stores_null(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()

    sqlite_storage.insert_job(job_id, max_scenes=None, transaction_id="tx")

    assert sqlite_storage.fetch_job(job_id)[0].max_scenes is None  # ty: ignore[not-subscriptable]


def test_update_expected_scenes_reports_whether_the_job_exists(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()
    sqlite_storage.insert_job(job_id, None, "tx")

    updated = sqlite_storage.update_expected_scenes(job_id, 7)
    missing = sqlite_storage.update_expected_scenes(uuid4(), 7)

    assert updated is True
    assert missing is False
    assert sqlite_storage.fetch_job(job_id)[0].expected_scenes == 7  # ty: ignore[not-subscriptable]


def test_completed_count_only_counts_descriptions_of_that_job(sqlite_storage: JobStorage) -> None:
    job_a, job_b = uuid4(), uuid4()
    for job_id in (job_a, job_b):
        sqlite_storage.insert_job(job_id, None, "tx")
    sqlite_storage.insert_description(job_a, _values(1))
    sqlite_storage.insert_description(job_a, _values(2))
    sqlite_storage.insert_description(job_b, _values(1))

    counts = {job_id: sqlite_storage.fetch_job(job_id)[1] for job_id in (job_a, job_b)}  # ty: ignore[not-subscriptable]

    assert counts == {job_a: 2, job_b: 1}


def test_redelivered_description_is_ignored_not_duplicated_or_overwritten(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()
    sqlite_storage.insert_job(job_id, None, "tx")
    sqlite_storage.insert_description(job_id, _values(1))

    sqlite_storage.insert_description(job_id, {**_values(1), "description": "a later, different caption"})
    [row] = sqlite_storage.fetch_descriptions(job_id)

    assert row.description == "description 1"
    assert sqlite_storage.fetch_job(job_id)[1] == 1  # ty: ignore[not-subscriptable]


def test_descriptions_table_declares_a_foreign_key_to_jobs() -> None:
    # SQLite doesn't enforce foreign keys by default, so assert the schema declares it rather than the engine.
    [foreign_key] = SceneDescriptionRow.__table__.foreign_keys

    assert foreign_key.target_fullname == "jobs.job_id"


def test_descriptions_are_ordered_by_scene_name(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()
    sqlite_storage.insert_job(job_id, None, "tx")
    for n in (3, 1, 2):
        sqlite_storage.insert_description(job_id, _values(n))

    rows = sqlite_storage.fetch_descriptions(job_id)

    assert [row.scene_name for row in rows] == ["scene-0001", "scene-0002", "scene-0003"]


def test_fetch_descriptions_of_unknown_job_is_empty(sqlite_storage: JobStorage) -> None:
    assert sqlite_storage.fetch_descriptions(uuid4()) == []


def test_ensure_schema_is_idempotent(sqlite_storage: JobStorage) -> None:
    job_id = uuid4()
    sqlite_storage.insert_job(job_id, None, "tx")

    sqlite_storage.ensure_schema()

    assert sqlite_storage.fetch_job(job_id) is not None


def test_description_insert_compiles_to_postgres_on_conflict_do_nothing() -> None:
    # The SQLite stand-in is lenient; this pins the SQL the real database receives.
    captured = []
    with mock.patch.object(storage, "create_engine"), mock.patch.object(storage, "sessionmaker") as sessionmaker:
        sessionmaker.return_value.return_value.__enter__.return_value.execute.side_effect = captured.append
        JobStorage("postgresql+psycopg://host/db").insert_description(uuid4(), _values(1))

    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (job_id, scene_token) DO NOTHING" in sql
