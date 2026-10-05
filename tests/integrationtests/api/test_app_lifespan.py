"""What the service builds at startup for each run mode, with no dependency overrides: what a deployed process runs."""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from backseat_driver.api.app import create_app
from backseat_driver.config import RunMode, VlmBackend
from backseat_driver.process.backend_captioner import BackendCaptioner
from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from backseat_driver.transport.in_process_job_queue import InProcessJobQueue
from backseat_driver.transport.job_store.sql_job_store import SqlJobStore
from tests.fakes import FakeHttpClient, make_settings


def test_the_distributed_mode_wires_the_real_adapters_without_connecting() -> None:
    # The default broker and database URLs point at nothing, so startup only succeeds if none of the adapters
    # connects while being constructed.
    settings = make_settings(vlm_backend=VlmBackend.HUGGINGFACE, mode=RunMode.DISTRIBUTED, dataset_bucket="nuscenes")

    with TestClient(create_app(settings)) as client:
        state = client.app.state.services
        health = client.get("/health")

    assert isinstance(state.captioner, BackendCaptioner)
    assert isinstance(state.job_queue, CeleryJobQueue)
    assert isinstance(state.job_store, SqlJobStore)
    assert isinstance(state.image_store, S3DatasetStore)
    assert health.status_code == HTTPStatus.OK


def test_the_monolith_is_the_default_and_needs_no_infrastructure() -> None:
    with TestClient(create_app(make_settings(vlm_backend=VlmBackend.HUGGINGFACE))) as client:
        state = client.app.state.services
        job_id = client.post("/jobs").json()["job_id"]
        job = client.get(f"/jobs/{job_id}")

    assert isinstance(state.job_queue, InProcessJobQueue)
    assert isinstance(state.job_store, SqlJobStore)
    assert job.status_code == HTTPStatus.OK


def test_the_distributed_mode_cannot_even_be_configured_without_a_dataset_bucket() -> None:
    with pytest.raises(ValueError, match="DATASET_BUCKET"):
        make_settings(vlm_backend=VlmBackend.HUGGINGFACE, mode=RunMode.DISTRIBUTED)


def test_the_http_client_stays_open_while_serving_and_is_closed_at_shutdown() -> None:
    http = FakeHttpClient()
    app = create_app(make_settings(vlm_backend=VlmBackend.HUGGINGFACE), build_http=lambda: http)

    with TestClient(app):
        open_while_serving = not http.closed

    assert open_while_serving
    assert http.closed
