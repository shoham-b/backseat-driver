from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import app
from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore


@pytest.fixture(scope="session")
def job_queue() -> FakeJobQueue:
    return FakeJobQueue()


@pytest.fixture(scope="session")
def job_store() -> FakeJobStore:
    return FakeJobStore()


@pytest.fixture(scope="session", autouse=True)
def _override_dependencies(job_queue: FakeJobQueue, job_store: FakeJobStore) -> Iterator[None]:
    """No test in this layer may reach a real model, broker or database."""
    app.dependency_overrides[get_captioner] = lambda: FakeCaptioner("a fake scene description")
    app.dependency_overrides[get_job_queue] = lambda: job_queue
    app.dependency_overrides[get_job_store] = lambda: job_store
    yield
    for dependency in (get_captioner, get_job_queue, get_job_store):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture(scope="session")
def client(_override_dependencies: None) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
async def async_client(_override_dependencies: None) -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
