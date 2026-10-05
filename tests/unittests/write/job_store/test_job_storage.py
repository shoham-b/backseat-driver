from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from backseat_driver.write.job_store.orm import SceneDescriptionRow
from backseat_driver.write.job_store.storage import JobStorage, description_insert


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


class _EngineFactory:
    """Stands in for sqlalchemy's `create_engine`: records each call and hands out `engine`."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._engine = engine or create_engine("sqlite://")

    def __call__(self, *args: Any, **kwargs: Any) -> Engine:
        self.calls.append((args, kwargs))
        return self._engine


def test_a_sqlite_engine_waits_on_a_locked_file_and_is_shareable_across_threads() -> None:
    engines = _EngineFactory()

    JobStorage("sqlite:///jobs.db", engine_factory=engines).ping()

    [(_, kwargs)] = engines.calls
    assert kwargs["connect_args"] == {"timeout": 10, "check_same_thread": False}


def test_constructing_storage_never_creates_an_engine() -> None:
    engines = _EngineFactory()

    JobStorage("postgresql+psycopg://host/db", engine_factory=engines)

    assert engines.calls == []


def test_engine_is_created_once_with_bounded_pool_and_fast_connect_timeout() -> None:
    engines = _EngineFactory()
    job_storage = JobStorage("postgresql+psycopg://host/db", engine_factory=engines)

    job_storage.ping()
    job_storage.ping()

    assert engines.calls == [
        (
            ("postgresql+psycopg://host/db",),
            {"pool_size": 4, "max_overflow": 0, "pool_pre_ping": True, "connect_args": {"connect_timeout": 10}},
        )
    ]


def test_ping_is_false_and_does_not_raise_when_database_is_unreachable() -> None:
    unreachable = create_engine("sqlite:////no/such/directory/jobs.db")

    reachable = JobStorage("postgresql+psycopg://host/db", engine_factory=_EngineFactory(unreachable)).ping()

    assert reachable is False


def test_ping_is_true_when_database_answers(sqlite_storage: JobStorage) -> None:
    assert sqlite_storage.ping() is True


def test_ping_propagates_unexpected_errors() -> None:
    def connect() -> Any:
        raise RuntimeError("not a database error")

    broken = create_engine("sqlite://", creator=connect)

    with pytest.raises(RuntimeError, match="not a database error"):
        JobStorage("postgresql+psycopg://host/db", engine_factory=_EngineFactory(broken)).ping()


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


def test_ensure_schema_rejects_a_table_from_an_older_schema() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE jobs (job_id CHAR(32) PRIMARY KEY, transaction_id VARCHAR)")
    storage = JobStorage("sqlite://", engine_factory=lambda *_, **__: engine)

    with pytest.raises(RuntimeError, match=r"'jobs'.*missing columns: .*idempotency_key"):
        storage.ensure_schema()


def test_description_insert_compiles_to_postgres_on_conflict_do_nothing() -> None:
    # The SQLite stand-in is lenient; this pins the SQL the real database receives.
    statement = description_insert(uuid4(), _values(1))

    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (job_id, scene_token, camera_channel) DO NOTHING" in sql


def test_a_descriptions_table_with_the_old_primary_key_is_rejected() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE scene_descriptions (job_id CHAR(32), scene_token VARCHAR, scene_name VARCHAR, "
            "camera_channel VARCHAR, image_path VARCHAR, description VARCHAR, model_name VARCHAR, "
            "reference_description VARCHAR, generated_at DATETIME, PRIMARY KEY (job_id, scene_token))"
        )
    job_storage = JobStorage("sqlite://", engine_factory=lambda *_, **__: engine)

    with pytest.raises(RuntimeError) as raised:
        job_storage.ensure_schema()

    message = str(raised.value)
    assert "'scene_descriptions'" in message
    assert "primary key ['job_id', 'scene_token'], expected ['camera_channel', 'job_id', 'scene_token']" in message
    assert "missing columns" not in message
