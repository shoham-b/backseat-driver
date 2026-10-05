import json
from typing import Any
from uuid import uuid4

import pytest

from backseat_driver.models import JobState
from backseat_driver.process.http_client import HttpResponse
from backseat_driver.transport.api_client import ApiJobClient
from tests.fakes import FakeHttpClient, make_keyframe

API = "http://api:8080"
JOB_ID = str(uuid4())


def _job(state: JobState, completed: int = 0) -> dict[str, Any]:
    return {
        "job_id": JOB_ID,
        "transaction_id": "tx",
        "state": state.value,
        "max_scenes": None,
        "expected_scenes": 2,
        "completed_scenes": completed,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _json(body: Any) -> HttpResponse:
    return HttpResponse(json.dumps(body).encode(), "application/json")


def _description(n: int) -> dict[str, Any]:
    return {
        **make_keyframe(n).model_dump(),
        "description": f"scene {n}",
        "model_name": "m",
        "generated_at": "2026-01-01T00:00:00Z",
    }


class _Clock:
    """Time that only moves when the client sleeps, so a timeout test takes no real time."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _client(http: FakeHttpClient, clock: _Clock | None = None) -> ApiJobClient:
    clock = clock or _Clock()
    return ApiJobClient(API, http=http, sleep=clock.sleep, clock=clock)


def test_a_job_that_is_already_completed_is_not_polled() -> None:
    http = FakeHttpClient(response=_job(JobState.COMPLETED, completed=2))
    http.responses_by_url[f"{API}/jobs/{JOB_ID}/descriptions"] = _json([_description(0), _description(1)])

    descriptions = _client(http).describe(max_scenes=None, timeout_seconds=10)

    assert [d.description for d in descriptions] == ["scene 0", "scene 1"]
    assert [probe.url for probe in http.gets] == [f"{API}/jobs/{JOB_ID}/descriptions"]


def test_a_failed_job_raises_with_its_error_instead_of_polling_until_the_timeout() -> None:
    http = FakeHttpClient(response=_job(JobState.PENDING))
    http.responses_by_url[f"{API}/jobs/{JOB_ID}"] = _json({**_job(JobState.FAILED), "error": "caption failed: boom"})

    with pytest.raises(RuntimeError, match="failed: caption failed: boom"):
        _client(http).describe(max_scenes=None, timeout_seconds=10)


def test_a_running_job_is_polled_until_it_is_completed() -> None:
    http = FakeHttpClient(response=_job(JobState.PENDING))
    http.sequences_by_url[f"{API}/jobs/{JOB_ID}"] = [
        _json(_job(JobState.RUNNING, completed=0)),
        _json(_job(JobState.RUNNING, completed=1)),
        _json(_job(JobState.COMPLETED, completed=2)),
    ]
    http.responses_by_url[f"{API}/jobs/{JOB_ID}/descriptions"] = _json([_description(0)])
    seen: list[tuple[JobState, int]] = []

    descriptions = _client(http).describe(
        max_scenes=None, timeout_seconds=10, on_progress=lambda j: seen.append((j.state, j.completed_scenes))
    )

    assert len(descriptions) == 1
    assert seen == [(JobState.RUNNING, 0), (JobState.RUNNING, 1), (JobState.COMPLETED, 2)]


def test_max_scenes_is_sent_with_the_job() -> None:
    http = FakeHttpClient(response=_job(JobState.COMPLETED))
    http.responses_by_url[f"{API}/jobs/{JOB_ID}/descriptions"] = _json([])

    _client(http).describe(max_scenes=3, timeout_seconds=10)

    assert [(post.url, post.payload) for post in http.posts] == [(f"{API}/jobs", {"max_scenes": 3})]


def test_a_job_that_never_finishes_fails_after_the_timeout() -> None:
    http = FakeHttpClient(response=_job(JobState.PENDING))
    http.responses_by_url[f"{API}/jobs/{JOB_ID}"] = _json(_job(JobState.RUNNING, completed=1))

    with pytest.raises(RuntimeError, match="still running"):
        _client(http).describe(max_scenes=None, timeout_seconds=5, poll_seconds=2)
