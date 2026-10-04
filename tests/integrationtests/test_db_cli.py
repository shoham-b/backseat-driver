from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.config import get_settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_db_init_creates_the_job_tables_and_is_idempotent(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    env = {"BACKSEAT_DRIVER_DATABASE_URL": url}

    first = runner.invoke(app, ["db", "init"], env=env)
    second = runner.invoke(app, ["db", "init"], env=env)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert inspect(create_engine(url)).get_table_names()
