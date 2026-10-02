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


@pytest.fixture(autouse=True)
def _never_download_nuscenes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run` fetches the dataset when its cache is stale; no test may reach the network (or wipe a fixture dataroot).

    Patches the attribute on the module, so tests that imported the real function directly are unaffected.
    """
    monkeypatch.setattr("backseat_driver.scenes.nuscenes_dataset.ensure_nuscenes_dataset", lambda *args, **kwargs: None)
