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
    def healthcheck(self) -> bool:
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
    """Records whether its health check ran on the event loop's thread (where a running loop is visible)."""

    def __init__(self) -> None:
        super().__init__()
        self.ran_on_the_event_loop: bool | None = None

    def healthcheck(self) -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.ran_on_the_event_loop = False
        else:
            self.ran_on_the_event_loop = True
        return True


def test_readiness_probes_the_captioner_off_the_event_loop(client_with: ClientFactory) -> None:
    captioner = _LoopProbingCaptioner()
    client = client_with({get_captioner: lambda: captioner})

    response = client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert captioner.ran_on_the_event_loop is False
