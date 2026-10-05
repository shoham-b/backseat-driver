"""Reads the jobs a report shows from the API instead of from result files.

A job's descriptions come from `GET /jobs/{id}/descriptions` and each scene's image from `GET /images/{key}`, so the
report needs the API and nothing else: not the dataset, not the database, not the bucket.
"""

from collections.abc import Sequence
from urllib.parse import quote

from backseat_driver.api.client import IMAGES_PATH, ApiClient
from backseat_driver.models import JobState, SceneDescription
from backseat_driver.process.http_client import HttpClient, HttpResponse
from backseat_driver.show.description_source import DescriptionSource

__all__ = ["IMAGES_PATH", "ApiReportSource"]

# The most jobs the API lists at once.
_MAX_JOBS = 500


class ApiReportSource(DescriptionSource):
    """The API as a source: the given jobs, or with no `job_ids` every completed job."""

    def __init__(self, api_url: str, http: HttpClient, job_ids: Sequence[str] | None = None) -> None:
        self._api = ApiClient(api_url, http)
        self._job_ids = job_ids

    async def descriptions(self) -> list[SceneDescription]:
        if self._job_ids is None:
            return await self.all_descriptions()
        return [d for job_id in self._job_ids for d in await self.job_descriptions(job_id)]

    async def job_descriptions(self, job_id: str) -> list[SceneDescription]:
        """The finished job's descriptions; a job still running is an error, not a partial report."""
        job = await self._api.get_job(job_id)
        if job.state is not JobState.COMPLETED:
            raise RuntimeError(
                f"job {job_id} is {job.state.value} ({job.completed_scenes}/{job.expected_scenes} descriptions); "
                "wait until it is completed"
            )
        return await self._api.descriptions(job_id)

    async def all_descriptions(self) -> list[SceneDescription]:
        """The descriptions of every completed job, the newest job winning where several ran the same model."""
        latest: dict[tuple[str, str, str], SceneDescription] = {}
        for job in await self._api.list_jobs(JobState.COMPLETED, _MAX_JOBS):
            for description in await self._api.descriptions(str(job.job_id)):
                identity = (description.model_name, description.scene_token, description.camera_channel)
                latest.setdefault(identity, description)
        return list(latest.values())

    async def image(self, image_path: str) -> HttpResponse:
        return await self._api.image(image_path)

    def image_link(self, image_path: str) -> str | None:
        return f"{IMAGES_PATH}{quote(image_path)}"
