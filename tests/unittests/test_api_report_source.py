import base64
import json
from typing import Any
from uuid import uuid4

import pytest

from backseat_driver.captioning.http_client import HttpResponse
from backseat_driver.models import JobState
from backseat_driver.reporting.api_source import ApiReportSource
from tests.fakes import FakeHttpClient, make_keyframe

API = "http://api:8080"


def _job(job_id: str, state: JobState, completed: int = 2) -> HttpResponse:
    body = {
        "job_id": job_id,
        "transaction_id": "tx",
        "state": state.value,
        "max_scenes": None,
        "expected_scenes": 2,
        "completed_scenes": completed,
        "created_at": "2026-01-01T00:00:00Z",
    }
    return HttpResponse(json.dumps(body).encode(), "application/json")


def _description(n: int) -> dict[str, Any]:
    keyframe = make_keyframe(n)
    return {
        "scene_token": keyframe.scene_token,
        "scene_name": keyframe.scene_name,
        "camera_channel": keyframe.camera_channel,
        "image_path": f"samples/CAM_FRONT/{n}.jpg",
        "description": "a road",
        "model_name": "m",
    }


def test_the_descriptions_of_a_completed_job_come_from_the_api() -> None:
    job_id, http = str(uuid4()), FakeHttpClient()
    http.responses_by_url = {
        f"{API}/jobs/{job_id}": _job(job_id, JobState.COMPLETED),
        f"{API}/jobs/{job_id}/descriptions": HttpResponse(json.dumps([_description(1)]).encode(), "application/json"),
    }

    descriptions = ApiReportSource(API + "/", http).descriptions(job_id)

    assert [d.image_path for d in descriptions] == ["samples/CAM_FRONT/1.jpg"]


def test_a_job_that_is_still_running_is_an_error_not_a_partial_report() -> None:
    job_id, http = str(uuid4()), FakeHttpClient()
    http.responses_by_url = {f"{API}/jobs/{job_id}": _job(job_id, JobState.RUNNING, completed=1)}

    with pytest.raises(RuntimeError, match=r"running \(1/2 scenes\)"):
        ApiReportSource(API, http).descriptions(job_id)

    assert [probe.url for probe in http.gets] == [f"{API}/jobs/{job_id}"]


def test_an_image_is_returned_as_a_data_uri_of_the_served_bytes() -> None:
    http = FakeHttpClient()
    http.responses_by_url = {f"{API}/images/samples/CAM_FRONT/a.jpg": HttpResponse(b"jpeg", "image/jpeg")}

    uri = ApiReportSource(API, http).image("samples/CAM_FRONT/a.jpg")

    assert uri == "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode()
