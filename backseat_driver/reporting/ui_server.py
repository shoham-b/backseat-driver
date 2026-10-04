"""The report UI as a small HTTP server that builds its page on every load.

Descriptions come from result files (images inlined from the local paths in them) and/or from the API (completed
jobs; their images are fetched through this server's `/images/` route, which proxies the API, so the browser only ever
talks to the UI). Nothing is mounted: a deployed UI needs the API's address and nothing else, and a new job shows up
on the next page load.
"""

import json
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from loguru import logger

from backseat_driver.captioning.http_client import HttpStatusError
from backseat_driver.datasets.image_keys import validate_image_key
from backseat_driver.errors import UnprocessableError
from backseat_driver.models import SceneDescription
from backseat_driver.reporting.api_source import ApiReportSource
from backseat_driver.reporting.html_report_writer import file_data_uri, render_html
from backseat_driver.reporting.report import build_report

_IMAGES = "/images/"
_IMMUTABLE = "public, max-age=86400, immutable"


class ReportPage:
    """Builds the report from its sources each time it is asked for."""

    def __init__(
        self,
        result_files: list[Path],
        source: ApiReportSource | None = None,
        job_ids: list[str] | None = None,
        all_jobs: bool = False,
        live_api_url: str | None = None,
    ) -> None:
        self._result_files = result_files
        self._source = source
        self._job_ids = job_ids or []
        self._all_jobs = all_jobs
        self._live_api_url = live_api_url

    def render(self) -> tuple[str, int]:
        """The page and how many descriptions it shows."""
        descriptions = [
            SceneDescription.model_validate(item)
            for path in self._result_files
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]
        from_api: list[SceneDescription] = []
        if self._source is not None:
            for job_id in self._job_ids:
                from_api += self._source.descriptions(job_id)
            if self._all_jobs:
                from_api += self._source.all_descriptions()
        api_keys = {d.image_path for d in from_api}

        def read_image(image_path: str) -> str:
            # A job's image_path is a dataset key the API serves; a result file's is a local path.
            return f"{_IMAGES}{quote(image_path)}" if image_path in api_keys else file_data_uri(image_path)

        descriptions += from_api
        return render_html(build_report(descriptions), self._live_api_url, read_image), len(descriptions)


def make_handler(page: ReportPage, source: ApiReportSource | None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/healthz":  # liveness without touching the API, which a probe must not depend on
                self._send(HTTPStatus.OK, b"ok", "text/plain")
            elif path in ("/", "/index.html"):
                self._guarded(self._page)
            elif path.startswith(_IMAGES) and source is not None:
                self._guarded(lambda: self._image(source, unquote(path.removeprefix(_IMAGES))))
            else:
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

        def _page(self) -> None:
            html, _ = page.render()
            self._send(HTTPStatus.OK, html.encode(), "text/html; charset=utf-8")

        def _image(self, api: ApiReportSource, key: str) -> None:
            validate_image_key(key)
            response = api.image_response(key)
            self._send(HTTPStatus.OK, response.body, response.content_type, {"Cache-Control": _IMMUTABLE})

        def _guarded(self, action: Callable[[], None]) -> None:
            try:
                action()
            except UnprocessableError as exc:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc).encode(), "text/plain")
            except HttpStatusError as exc:
                # The API's own answer (a missing image stays a 404); anything else upstream is a bad gateway.
                status = HTTPStatus.NOT_FOUND if exc.status == HTTPStatus.NOT_FOUND else HTTPStatus.BAD_GATEWAY
                self._send(status, str(exc).encode(), "text/plain")
            except (RuntimeError, OSError) as exc:
                logger.warning("report page failed: {}", exc)
                self._send(HTTPStatus.BAD_GATEWAY, str(exc).encode(), "text/plain")

        def _send(
            self, status: HTTPStatus, body: bytes, content_type: str, headers: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler
