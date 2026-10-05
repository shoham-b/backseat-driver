from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from backseat_driver.config import get_settings
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore, make_settings
from tests.stub_server import Responder, StubServer

ClientFactory = Callable[..., TestClient]


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    """The CLI commands read `get_settings()`, which is cached; a test's environment must not outlive it."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _run_outside_the_repo(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings read `./.env`; an empty working directory keeps a developer's own file out of these tests.

    The commands under test take their configuration from the `env` each test passes, not from the machine.
    """
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


@pytest.fixture
def stub_server() -> Iterator[Callable[[Responder], StubServer]]:
    """Starts a server answering with the given function; every server started is stopped when the test ends."""
    servers: list[StubServer] = []

    def start(respond: Responder) -> StubServer:
        servers.append(StubServer(respond))
        return servers[-1]

    yield start
    for server in servers:
        server.stop()


@pytest.fixture
def job_queue() -> FakeJobQueue:
    return FakeJobQueue()


@pytest.fixture
def job_store() -> FakeJobStore:
    return FakeJobStore()


@pytest.fixture
def app(job_queue: FakeJobQueue, job_store: FakeJobStore) -> FastAPI:
    """A service whose model, broker and database are fakes, so no test in this layer reaches the real ones.

    Fresh for every test: the queue and store record what happened, so sharing them would let one test see another's.
    """
    service = create_app(make_settings())
    service.dependency_overrides[get_captioner] = lambda: FakeCaptioner("a fake scene description")
    service.dependency_overrides[get_job_queue] = lambda: job_queue
    service.dependency_overrides[get_job_store] = lambda: job_store
    return service


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with() -> ClientFactory:
    """A client over a fresh service of fakes, with `overrides` layered on top, for a test that swaps a collaborator."""

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
