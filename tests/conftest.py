import os
from collections.abc import Iterator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--api-url", default="http://localhost:8080", help="Target of the smoke and system tests")


def pytest_configure(config: pytest.Config) -> None:
    """Drop the app's own configuration from the environment before anything reads it.

    `no_ambient_settings` hides these variables for each unit and integration test. This covers what that cannot:
    collection, because importing `backseat_driver.api.app` already builds a `Settings`, and the UI and smoke tests,
    whose subprocess and target would otherwise inherit a developer's variables. It does not stop `Settings` reading a
    `./.env` file; tests that go through `get_settings()` run from an empty directory for that (see
    `tests/integrationtests/conftest.py`).
    """
    for name in [name for name in os.environ if name.startswith("BACKSEAT_DRIVER_")]:
        del os.environ[name]


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    """Target of the smoke/system tests; `backseat-driver test smoke --api-url` passes it on as `--api-url`."""
    return str(request.config.getoption("--api-url"))


@pytest.fixture
def no_ambient_settings() -> Iterator[None]:
    """Hides the `BACKSEAT_DRIVER_*` variables, so `Settings` sees only what a test hands it.

    `just` exports `.env` into every recipe's environment, and a variable beats a default, so a developer's backend
    or model choice would otherwise change what the tests assert.
    """
    hidden = {name: os.environ.pop(name) for name in list(os.environ) if name.startswith("BACKSEAT_DRIVER_")}
    yield
    os.environ.update(hidden)
