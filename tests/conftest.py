import os

import pytest

from backseat_driver.config import Settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--api-url",
        default=os.environ.get("API_URL", "http://localhost:8080"),
        help="Base URL for smoke/system tests (also reads API_URL env var)",
    )


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    return str(request.config.getoption("--api-url"))
