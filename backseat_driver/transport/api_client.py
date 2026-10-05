"""Describes the dataset by submitting a job to a running API and waiting for the workers to finish it.

This is how the `describe` command runs the same read-process-write pipeline in `distributed` mode: the API enqueues
an ingest task, the ingest and caption workers do the steps, and the client only collects the finished descriptions.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from backseat_driver.api.client import ApiClient
from backseat_driver.models import Job, JobState, SceneDescription
from backseat_driver.process.http_client import HttpClient


class ApiJobClient:
    def __init__(
        self,
        api_url: str,
        http: HttpClient,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api = ApiClient(api_url, http)
        self._sleep = sleep
        self._clock = clock

    async def describe(
        self,
        max_scenes: int | None,
        timeout_seconds: float,
        poll_seconds: float = 2.0,
        on_progress: Callable[[Job], None] | None = None,
    ) -> list[SceneDescription]:
        """Submit a job and return its descriptions once it is completed; raise if it takes longer than the timeout."""
        job = await self._api.create_job(max_scenes)
        deadline = self._clock() + timeout_seconds
        while job.state is not JobState.COMPLETED:
            if job.state is JobState.FAILED:
                raise RuntimeError(f"job {job.job_id} failed: {job.error}")
            if self._clock() >= deadline:
                raise RuntimeError(
                    f"job {job.job_id} is still {job.state.value} "
                    f"({job.completed_scenes}/{job.expected_scenes} descriptions) after {timeout_seconds:g}s"
                )
            await self._sleep(poll_seconds)
            job = await self._api.get_job(str(job.job_id))
            if on_progress:
                on_progress(job)
        return await self._api.descriptions(str(job.job_id))
