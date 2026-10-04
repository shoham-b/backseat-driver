"""The report UI as a small FastAPI app that builds its page on every load.

Descriptions come from result files (images inlined from the local paths in them) and/or from the API (completed
jobs; their images are fetched through this app's `/images/` route, which proxies the API, so the browser only ever
talks to the UI). Nothing is mounted: a deployed UI needs the API's address and nothing else, and a new job shows up
on the next page load.
"""

import json
from http import HTTPStatus
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from backseat_driver.datasets.image_keys import validate_image_key
from backseat_driver.error_format import error_body
from backseat_driver.errors import HttpStatusError, UnprocessableError
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


def get_page(request: Request) -> ReportPage:
    return request.app.state.page  # type: ignore[no-any-return]


def get_source(request: Request) -> ApiReportSource:
    return request.app.state.source  # type: ignore[no-any-return]


def _json_error(status: HTTPStatus, message: str) -> JSONResponse:
    # The same JSON envelope the API answers errors in.
    return JSONResponse(status_code=status, content=error_body(status, message))


async def _unprocessable(request: Request, exc: UnprocessableError) -> JSONResponse:
    return _json_error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))


async def _upstream_status(request: Request, exc: HttpStatusError) -> JSONResponse:
    # The API's own answer (a missing image stays a 404); anything else upstream is a bad gateway.
    status = HTTPStatus.NOT_FOUND if exc.status == HTTPStatus.NOT_FOUND else HTTPStatus.BAD_GATEWAY
    return _json_error(status, str(exc))


async def _upstream_failure(request: Request, exc: RuntimeError | OSError) -> JSONResponse:
    logger.warning("report page failed: {}", exc)
    return _json_error(HTTPStatus.BAD_GATEWAY, str(exc))


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _json_error(HTTPStatus(exc.status_code), str(exc.detail))


def create_ui_app(page: ReportPage, source: ApiReportSource | None) -> FastAPI:
    """The UI for `page`; `source` is the API the images come from (none: there is no `/images/` route)."""
    app = FastAPI(title="Backseat Driver report UI", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.page = page
    app.state.source = source
    app.add_exception_handler(UnprocessableError, _unprocessable)  # type: ignore
    app.add_exception_handler(HttpStatusError, _upstream_status)  # type: ignore
    app.add_exception_handler(RuntimeError, _upstream_failure)  # type: ignore
    app.add_exception_handler(OSError, _upstream_failure)  # type: ignore
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore

    @app.get("/healthz")
    def healthz() -> PlainTextResponse:
        # Liveness without touching the API, which a probe must not depend on.
        return PlainTextResponse("ok")

    # Plain `def` routes: rendering and proxying do blocking HTTP and file reads, which FastAPI runs in a thread.
    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    def index(report_page: Annotated[ReportPage, Depends(get_page)]) -> HTMLResponse:
        html, _ = report_page.render()
        return HTMLResponse(html)

    if source is not None:

        @app.get("/images/{key:path}")
        def image(key: str, api: Annotated[ApiReportSource, Depends(get_source)]) -> Response:
            validate_image_key(key)
            response = api.image_response(key)
            return Response(response.body, media_type=response.content_type, headers={"Cache-Control": _IMMUTABLE})

    return app
