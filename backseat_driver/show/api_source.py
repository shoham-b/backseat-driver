"""Reads the jobs a report shows from the API instead of from result files.

A job's descriptions come from `GET /jobs/{id}/descriptions` and each scene's image from `GET /images/{key}`, so the
report needs the API and nothing else: not the dataset, not the database, not the bucket.
"""

import json
from collections.abc import Sequence
from urllib.parse import quote

from backseat_driver.models import Job, JobState, SceneDescription
from backseat_driver.process.http_client import HttpClient, HttpResponse, UrllibHttpClient
from backseat_driver.show.description_source import DescriptionSource

_TIMEOUT_SECONDS = 30.0

# The UI serves an image at the same path the API does, so a page can link to its own host.
IMAGES_PATH = "/images/"


class ApiReportSource(DescriptionSource):
    """The API as a source: the given jobs, or with no `job_ids` every completed job."""

    def __init__(self, api_url: str, http: HttpClient | None = None, job_ids: Sequence[str] | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._http = http or UrllibHttpClient()
        self._job_ids = job_ids

    def descriptions(self) -> list[SceneDescription]:
        if self._job_ids is None:
            return self.all_descriptions()
        return [d for job_id in self._job_ids for d in self.job_descriptions(job_id)]

    def job_descriptions(self, job_id: str) -> list[SceneDescription]:
        """The finished job's descriptions; a job still running is an error, not a partial report."""
        job = Job.model_validate_json(self._get(f"/jobs/{quote(job_id)}").body)
        if job.state is not JobState.COMPLETED:
            raise RuntimeError(
                f"job {job_id} is {job.state.value} ({job.completed_scenes}/{job.expected_scenes} descriptions); "
                "wait until it is completed"
            )
        return self._descriptions_of(job_id)

    def all_descriptions(self) -> list[SceneDescription]:
        """The descriptions of every completed job, the newest job winning where several ran the same model."""
        seen: set[tuple[str, str, str]] = set()
        latest: list[SceneDescription] = []
        for job in self._completed_jobs():
            for description in self._descriptions_of(str(job.job_id)):
                identity = (description.model_name, description.scene_token, description.camera_channel)
                if identity not in seen:
                    seen.add(identity)
                    latest.append(description)
        return latest

    def image(self, image_path: str) -> HttpResponse:
        return self._get(f"{IMAGES_PATH}{quote(image_path)}")

    def image_link(self, image_path: str) -> str | None:
        return f"{IMAGES_PATH}{quote(image_path)}"

    def _completed_jobs(self) -> list[Job]:
        body = self._get(f"/jobs?state={JobState.COMPLETED.value}&limit=500").body
        return [Job.model_validate(item) for item in json.loads(body)]

    def _descriptions_of(self, job_id: str) -> list[SceneDescription]:
        items = json.loads(self._get(f"/jobs/{quote(job_id)}/descriptions").body)
        return [SceneDescription.model_validate(item) for item in items]

    def _get(self, path: str) -> HttpResponse:
        return self._http.get(f"{self._api_url}{path}", {}, _TIMEOUT_SECONDS, "the API")
