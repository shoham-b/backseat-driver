import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from backseat_driver.config import Settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--api-url", default="http://localhost:8080", help="Target of the smoke and system tests")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    """Target of the smoke/system tests; `backseat-driver test smoke --api-url` passes it on as `--api-url`."""
    return str(request.config.getoption("--api-url"))


@pytest.fixture
def no_ambient_settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Hides every source of `Settings` a developer has, so a test sees only what it hands in.

    That is the `BACKSEAT_DRIVER_*` variables (`just` exports `.env` into every recipe's environment, and a variable
    beats a default) and the `.env` file itself, which the CLI reads from the working directory: the test runs from an
    empty one instead.
    """
    hidden = {name: os.environ.pop(name) for name in list(os.environ) if name.startswith("BACKSEAT_DRIVER_")}
    previous_directory = Path.cwd()
    os.chdir(tmp_path_factory.mktemp("cwd"))
    yield
    os.chdir(previous_directory)
    os.environ.update(hidden)
