import os
from collections.abc import Iterator

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
def no_ambient_settings() -> Iterator[None]:
    """Hides the `BACKSEAT_DRIVER_*` variables, so `Settings` sees only what a test hands it.

    `just` exports `.env` into every recipe's environment, and a variable beats a default, so a developer's backend
    or model choice would otherwise change what the tests assert.
    """
    hidden = {name: os.environ.pop(name) for name in list(os.environ) if name.startswith("BACKSEAT_DRIVER_")}
    yield
    os.environ.update(hidden)
