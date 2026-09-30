from http import HTTPStatus

import httpx


def test_liveness(smoke_client: httpx.Client) -> None:
    response = smoke_client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"


def test_readiness(smoke_client: httpx.Client) -> None:
    response = smoke_client.get("/ready")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "ok"
