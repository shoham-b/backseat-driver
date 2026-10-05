import asyncio
from collections.abc import Callable
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.dependencies import get_captioner, get_job_queue, get_job_store
from backseat_driver.process.captioner import Captioner
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore
from tests.integrationtests.conftest import ClientFactory


class _UnhealthyCaptioner(FakeCaptioner):
    async def healthcheck(self) -> bool:
        return False


def test_liveness(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_request_id_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health")

    assert "x-request-id" in response.headers


def test_request_id_propagated_from_request(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "my-trace-id"})

    assert response.headers["x-request-id"] == "my-trace-id"


def test_readiness_healthy(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_readiness_unhealthy_backend(client_with: ClientFactory) -> None:
    client = client_with({get_captioner: lambda: _UnhealthyCaptioner()})

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.SERVICE_UNAVAILABLE
    assert error["status"] == HTTPStatus.SERVICE_UNAVAILABLE.phrase
    assert "message" in error


def test_error_response_shape_on_unhandled_exception(client_with: ClientFactory) -> None:
    def _raise() -> Captioner:
        raise RuntimeError("boom")

    client = client_with({get_captioner: _raise}, raise_server_exceptions=False)

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert error["status"] == HTTPStatus.INTERNAL_SERVER_ERROR.phrase
    assert "message" in error


@pytest.mark.parametrize(
    ("dependency", "unhealthy"),
    [(get_job_queue, FakeJobQueue(healthy=False)), (get_job_store, FakeJobStore(healthy=False))],
)
def test_readiness_unhealthy_queue_or_store(
    client_with: ClientFactory, dependency: Callable[..., object], unhealthy: object
) -> None:
    client = client_with({dependency: lambda: unhealthy})

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


class _LoopProbingCaptioner(FakeCaptioner):
    """Records which event loop its health check ran on."""

    def __init__(self) -> None:
        super().__init__()
        self.loop_id: int | None = None

    async def healthcheck(self) -> bool:
        self.loop_id = id(asyncio.get_running_loop())
        return True


def test_readiness_probes_the_captioner_off_the_servers_event_loop(client_with: ClientFactory) -> None:
    captioner = _LoopProbingCaptioner()
    server_loops: list[int] = []

    async def store_on_the_servers_loop() -> FakeJobStore:
        server_loops.append(id(asyncio.get_running_loop()))
        return FakeJobStore()

    client = client_with({get_captioner: lambda: captioner, get_job_store: store_on_the_servers_loop})

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert captioner.loop_id is not None
    assert captioner.loop_id != server_loops[0]
