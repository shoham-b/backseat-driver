import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--api-url", default="http://localhost:8080", help="Target of the smoke and system tests")


def pytest_configure(config: pytest.Config) -> None:
    """Drop the app's own configuration from the environment before anything reads it.

    `just` loads `.env` into the environment and developers export these variables, but a test's configuration is
    what the test passes in. This runs before collection because importing `backseat_driver.api.app` already builds a
    `Settings`. It does not stop `Settings` reading a `./.env` file; tests that go through `get_settings()` run from
    an empty directory for that (see `tests/integrationtests/conftest.py`).
    """
    for name in [name for name in os.environ if name.startswith("BACKSEAT_DRIVER_")]:
        del os.environ[name]


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    """Target of the smoke/system tests; `backseat-driver test smoke --api-url` passes it on as `--api-url`."""
    return str(request.config.getoption("--api-url"))
