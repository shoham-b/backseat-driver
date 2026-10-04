"""The report UI as a small FastAPI app that builds its page on every load.

Descriptions come from the result files in the output directory (images inlined from the local dataroot) and/or,
with `BACKSEAT_DRIVER_UI_ALL_JOBS`, from the API's completed jobs; their images are fetched through this app's
`/images/` route, which proxies the API, so the browser only ever talks to the UI. Nothing is mounted: a deployed UI
needs the API's address and nothing else, and a new job or result file shows up on the next page load.

Run it like the API: `fastapi run backseat_driver/show/ui_server.py` (`just ui`).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from backseat_driver.config import Settings, get_settings
from backseat_driver.error_format import error_body
from backseat_driver.errors import HttpStatusError, UnprocessableError
from backseat_driver.read.images.image_keys import validate_image_key
from backseat_driver.read.images.local_image_store import LocalImageStore
from backseat_driver.show.api_source import IMAGES_PATH, ApiReportSource
from backseat_driver.show.description_source import DescriptionSource
from backseat_driver.show.report_service import ReportService
from backseat_driver.show.result_file_source import ResultFileSource

_IMMUTABLE = "public, max-age=86400, immutable"


def get_settings_dependency(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_source(settings: Annotated[Settings, Depends(get_settings_dependency)]) -> ApiReportSource | None:
    return ApiReportSource(settings.api_url) if settings.ui_all_jobs else None


def get_report_service(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    source: Annotated[ApiReportSource | None, Depends(get_source)],
) -> ReportService:
    images = LocalImageStore(settings.nuscenes_dataroot)
    sources: list[DescriptionSource] = [ResultFileSource.in_directory(Path(settings.output_dir), images)]
    if source is not None:
        sources.append(source)
    return ReportService(sources, settings.ui_public_api_url or settings.api_url)


def get_image_source(source: Annotated[ApiReportSource | None, Depends(get_source)]) -> ApiReportSource:
    if source is None:
        raise StarletteHTTPException(HTTPStatus.NOT_FOUND, "not found")
    return source


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


def _require_something_to_show(settings: Settings) -> None:
    if not settings.ui_all_jobs and not any(Path(settings.output_dir).glob("*.json")):
        raise ValueError(
            f"no result files in {settings.output_dir}; run `backseat-driver describe` first "
            "or set BACKSEAT_DRIVER_UI_ALL_JOBS=true to read the API's jobs"
        )


def create_ui_app(settings: Settings) -> FastAPI:
    """The UI for `settings`; tests swap `get_source` through `dependency_overrides` instead of patching."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        _require_something_to_show(settings)
        yield

    app = FastAPI(title="Backseat Driver report UI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
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
    def index(service: Annotated[ReportService, Depends(get_report_service)]) -> HTMLResponse:
        return HTMLResponse(service.render(embed_images=False).html)

    @app.get(f"{IMAGES_PATH}{{key:path}}")
    def image(key: str, api: Annotated[ApiReportSource, Depends(get_image_source)]) -> Response:
        validate_image_key(key)
        response = api.image(key)
        return Response(response.body, media_type=response.content_type, headers={"Cache-Control": _IMMUTABLE})

    return app


# `fastapi dev|run backseat_driver/show/ui_server.py` looks for this module-level `app`.
app = create_ui_app(get_settings())
