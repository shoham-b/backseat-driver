import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import settings

# Hypothesis' 200ms per-example deadline measures the machine, not the code: a loaded laptop or CI runner fails
# property tests of pure functions. What the properties assert does not depend on speed.
settings.register_profile("tests", deadline=None)
settings.load_profile("tests")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--api-url", default="http://localhost:8080", help="Target of the smoke and system tests")


def pytest_configure(config: pytest.Config) -> None:
    """Drop the app's own configuration from the environment before anything reads it.

    `no_ambient_settings` hides these variables, and the `.env` file, for each unit and integration test. This covers
    what that cannot: collection, because importing `backseat_driver.api.app` already builds a `Settings` (from the
    working directory's `.env` too, so an invalid one still breaks collection), and the UI and smoke tests, whose
    subprocess and target would otherwise inherit a developer's variables.
    """
    for name in [name for name in os.environ if name.startswith("BACKSEAT_DRIVER_")]:
        del os.environ[name]


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
