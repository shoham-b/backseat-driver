from collections.abc import AsyncGenerator, Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, make_settings

ClientFactory = Callable[..., TestClient]


@pytest.fixture(scope="session")
def job_queue() -> FakeJobQueue:
    return FakeJobQueue()


@pytest.fixture(scope="session")
def job_store() -> FakeJobStore:
    return FakeJobStore()


@pytest.fixture(scope="session")
def app(job_queue: FakeJobQueue, job_store: FakeJobStore):
    """A service whose model, broker and database are fakes, so no test in this layer reaches the real ones."""
    service = create_app(make_settings())
    service.dependency_overrides[get_captioner] = lambda: FakeCaptioner("a fake scene description")
    service.dependency_overrides[get_job_queue] = lambda: job_queue
    service.dependency_overrides[get_job_store] = lambda: job_store
    return service


@pytest.fixture(scope="session")
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
async def async_client(app) -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def client_with() -> ClientFactory:
    """A client over a fresh service of fakes, with `overrides` layered on top; the shared service is left untouched."""

    def build(
        overrides: dict[Callable[..., object], Callable[..., object]], raise_server_exceptions: bool = True
    ) -> TestClient:
        service = create_app(make_settings())
        service.dependency_overrides[get_captioner] = FakeCaptioner
        service.dependency_overrides[get_job_queue] = FakeJobQueue
        service.dependency_overrides[get_job_store] = FakeJobStore
        service.dependency_overrides.update(overrides)
        return TestClient(service, raise_server_exceptions=raise_server_exceptions)

    return build


@pytest.fixture(autouse=True)
def _hermetic_settings(no_ambient_settings: None) -> None:
    """Every test in this layer runs without the developer's settings."""
