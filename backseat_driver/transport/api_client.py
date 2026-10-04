"""Describes the dataset by submitting a job to a running API and waiting for the workers to finish it.

This is how the `describe` command runs the same read-process-write pipeline in `distributed` mode: the API enqueues
an ingest task, the ingest and caption workers do the steps, and the client only collects the finished descriptions.
"""

import json
import time
from collections.abc import Callable
from urllib.parse import quote

from backseat_driver.models import Job, JobState, SceneDescription
from backseat_driver.process.http_client import HttpClient, UrllibHttpClient

_REQUEST_TIMEOUT_SECONDS = 30.0


class ApiJobClient:
    def __init__(
        self,
        api_url: str,
        http: HttpClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._http = http or UrllibHttpClient()
        self._sleep = sleep
        self._clock = clock

    def describe(
        self,
        max_scenes: int | None,
        timeout_seconds: float,
        poll_seconds: float = 2.0,
        on_progress: Callable[[Job], None] | None = None,
    ) -> list[SceneDescription]:
        """Submit a job and return its descriptions once it is completed; raise if it takes longer than the timeout."""
        payload = {} if max_scenes is None else {"max_scenes": max_scenes}
        job = Job.model_validate(
            self._http.post_json(f"{self._api_url}/jobs", payload, {}, _REQUEST_TIMEOUT_SECONDS, "the API")
        )
        deadline = self._clock() + timeout_seconds
        while job.state is not JobState.COMPLETED:
            if job.state is JobState.FAILED:
                raise RuntimeError(f"job {job.job_id} failed: {job.error}")
            if self._clock() >= deadline:
                raise RuntimeError(
                    f"job {job.job_id} is still {job.state.value} "
                    f"({job.completed_scenes}/{job.expected_scenes} scenes) after {timeout_seconds:g}s"
                )
            self._sleep(poll_seconds)
            job = Job.model_validate_json(self._get(f"/jobs/{quote(str(job.job_id))}"))
            if on_progress:
                on_progress(job)
        items = json.loads(self._get(f"/jobs/{quote(str(job.job_id))}/descriptions"))
        return [SceneDescription.model_validate(item) for item in items]

    def _get(self, path: str) -> bytes:
        return self._http.get(f"{self._api_url}{path}", {}, _REQUEST_TIMEOUT_SECONDS, "the API").body
