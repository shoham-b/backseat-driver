import pytest

from backseat_driver.config import Settings

os.environ.setdefault("BACKSEAT_DRIVER_VLM_MODEL_NAME", "fake-model")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--api-url", default="http://localhost:8080", help="Target of the smoke and system tests")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def api_url(request: pytest.FixtureRequest) -> str:
    """Target of the smoke/system tests; `backseat-driver test smoke --api-url` passes it on as `--api-url`."""
    return str(request.config.getoption("--api-url"))
