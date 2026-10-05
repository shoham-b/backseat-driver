"""The API's own endpoints as typed calls, for the programs that talk to a running API.

`describe --mode distributed` (`transport.api_client`) and the report (`show.api_source`) both read jobs, descriptions
and images through this, so the paths, the quoting and the decoding live in one place.
"""

import json
from urllib.parse import quote, urlencode

from backseat_driver.models import Job, JobState, SceneDescription
from backseat_driver.process.http_client import HttpClient, HttpResponse, UrllibHttpClient

# Where the API serves an image by its dataset key; the report UI serves the same path itself, so a page can link to its
# own host.
IMAGES_PATH = "/images/"

_TIMEOUT_SECONDS = 30.0


class ApiClient:
    def __init__(self, api_url: str, http: HttpClient | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._http = http or UrllibHttpClient()

    def create_job(self, max_scenes: int | None) -> Job:
        payload = {} if max_scenes is None else {"max_scenes": max_scenes}
        body = self._http.post_json(f"{self._api_url}/jobs", payload, {}, _TIMEOUT_SECONDS, "the API")
        return Job.model_validate(body)

    def get_job(self, job_id: str) -> Job:
        return Job.model_validate_json(self._get(f"/jobs/{quote(job_id, safe='')}").body)

    def list_jobs(self, state: JobState | None = None, limit: int | None = None) -> list[Job]:
        query = urlencode({name: value for name, value in (("state", state), ("limit", limit)) if value is not None})
        body = self._get(f"/jobs?{query}" if query else "/jobs").body
        return [Job.model_validate(item) for item in json.loads(body)]

    def descriptions(self, job_id: str) -> list[SceneDescription]:
        items = json.loads(self._get(f"/jobs/{quote(job_id, safe='')}/descriptions").body)
        return [SceneDescription.model_validate(item) for item in items]

    def image(self, image_path: str) -> HttpResponse:
        return self._get(f"{IMAGES_PATH}{quote(image_path)}")

    def _get(self, path: str) -> HttpResponse:
        return self._http.get(f"{self._api_url}{path}", {}, _TIMEOUT_SECONDS, "the API")
