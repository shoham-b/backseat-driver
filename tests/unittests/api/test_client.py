import json
from typing import Any
from uuid import uuid4

import pytest

from backseat_driver.api.client import ApiClient
from backseat_driver.models import JobState
from backseat_driver.process.http_client import HttpResponse
from tests.fakes import FakeHttpClient

API = "http://api:8080"


def _job(job_id: str, state: JobState = JobState.COMPLETED) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "transaction_id": "tx",
        "state": state.value,
        "max_scenes": None,
        "expected_scenes": 1,
        "completed_scenes": 1,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _json(body: Any) -> HttpResponse:
    return HttpResponse(json.dumps(body).encode(), "application/json")


def test_creating_a_job_posts_the_scene_limit_when_there_is_one() -> None:
    http = FakeHttpClient(response=_job(str(uuid4())))

    ApiClient(API + "/", http).create_job(max_scenes=3)

    assert [(post.url, post.payload) for post in http.posts] == [(f"{API}/jobs", {"max_scenes": 3})]


def test_creating_a_job_without_a_limit_posts_an_empty_body() -> None:
    http = FakeHttpClient(response=_job(str(uuid4())))

    ApiClient(API, http).create_job(max_scenes=None)

    assert [post.payload for post in http.posts] == [{}]


@pytest.mark.parametrize(
    ("state", "limit", "query"),
    [
        (None, None, ""),
        (JobState.COMPLETED, None, "?state=completed"),
        (None, 5, "?limit=5"),
        (JobState.FAILED, 500, "?state=failed&limit=500"),
    ],
)
def test_listing_jobs_sends_only_the_filters_it_was_given(
    state: JobState | None, limit: int | None, query: str
) -> None:
    job_id = str(uuid4())
    http = FakeHttpClient()
    http.responses_by_url[f"{API}/jobs{query}"] = _json([_job(job_id)])

    jobs = ApiClient(API, http).list_jobs(state, limit)

    assert [str(job.job_id) for job in jobs] == [job_id]


def test_a_job_id_is_quoted_into_the_path() -> None:
    job_id = str(uuid4())
    http = FakeHttpClient()
    http.responses_by_url[f"{API}/jobs/a%2Fb"] = _json(_job(job_id))

    job = ApiClient(API, http).get_job("a/b")

    assert str(job.job_id) == job_id


def test_an_image_is_fetched_by_its_quoted_key() -> None:
    http = FakeHttpClient()
    http.responses_by_url[f"{API}/images/samples/CAM_FRONT/a%20b.jpg"] = HttpResponse(b"bytes", "image/jpeg")

    image = ApiClient(API, http).image("samples/CAM_FRONT/a b.jpg")

    assert (image.body, image.content_type) == (b"bytes", "image/jpeg")
