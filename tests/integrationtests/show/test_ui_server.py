"""The report UI app with a fake API behind it: pages are rebuilt per load, images proxied."""

import json
from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from backseat_driver.errors import HttpStatusError
from backseat_driver.process.http_client import HttpResponse
from backseat_driver.show.api_source import ApiReportSource
from backseat_driver.show.ui_server import create_ui_app, get_source
from tests.fakes import FakeHttpClient, make_settings

API = "http://api"
KEY = "samples/CAM_FRONT/a.jpg"
OUTPUT_DIR = Path(__file__).parent / "no_results"  # does not exist: the pages here come from the API only


def _job(job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "transaction_id": "tx",
        "state": "completed",
        "max_scenes": None,
        "expected_scenes": 1,
        "completed_scenes": 1,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _description(text: str, model: str = "model-a") -> dict[str, object]:
    return {
        "scene_token": "t",
        "scene_name": "scene-0001",
        "camera_channel": "CAM_FRONT",
        "image_path": KEY,
        "description": text,
        "model_name": model,
    }


def _json(value: object) -> HttpResponse:
    return HttpResponse(json.dumps(value).encode(), "application/json")


def _http_with_jobs(*jobs: tuple[str, list[dict[str, object]]]) -> FakeHttpClient:
    http = FakeHttpClient()
    http.responses_by_url = {
        f"{API}/jobs?state=completed&limit=500": _json([_job(job_id) for job_id, _ in jobs]),
        f"{API}/images/{KEY}": HttpResponse(b"jpeg bytes", "image/jpeg"),
        **{f"{API}/jobs/{job_id}/descriptions": _json(items) for job_id, items in jobs},
    }
    return http


def _ui(http: FakeHttpClient | None, all_jobs: bool = True) -> httpx.AsyncClient:
    settings = make_settings(api_url=API, ui_all_jobs=all_jobs, output_dir=str(OUTPUT_DIR))
    app = create_ui_app(settings)
    if http is not None:
        app.dependency_overrides[get_source] = lambda: ApiReportSource(API, http)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ui")


async def test_the_page_shows_the_completed_jobs_and_points_images_at_the_ui_itself() -> None:
    async with _ui(_http_with_jobs((str(uuid4()), [_description("a parked truck")]))) as ui:
        response = await ui.get("/")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["Content-Type"].startswith("text/html")
    assert b"a parked truck" in response.content
    assert b"/images/samples/CAM_FRONT/a.jpg" in response.content
    assert b"data:image" not in response.content


async def test_a_job_finished_after_startup_shows_up_on_the_next_load() -> None:
    http = _http_with_jobs((str(uuid4()), [_description("first job")]))
    async with _ui(http) as ui:
        assert b"second job" not in (await ui.get("/")).content
        second = str(uuid4())
        http.responses_by_url[f"{API}/jobs?state=completed&limit=500"] = _json([_job(second)])
        http.responses_by_url[f"{API}/jobs/{second}/descriptions"] = _json([_description("second job")])

        response = await ui.get("/")

    assert b"second job" in response.content


async def test_several_jobs_of_one_model_show_only_the_newest() -> None:
    newest, older = str(uuid4()), str(uuid4())
    http = _http_with_jobs((newest, [_description("new words")]), (older, [_description("old words")]))
    async with _ui(http) as ui:
        response = await ui.get("/")

    assert b"new words" in response.content
    assert b"old words" not in response.content


async def test_an_image_is_proxied_from_the_api_with_caching_headers() -> None:
    async with _ui(_http_with_jobs()) as ui:
        response = await ui.get(f"/images/{KEY}")

    assert (response.status_code, response.content, response.headers["Content-Type"]) == (
        HTTPStatus.OK,
        b"jpeg bytes",
        "image/jpeg",
    )
    assert "immutable" in response.headers["Cache-Control"]


@pytest.mark.parametrize("path", ["/images/v1.0-mini/scene.json", "/images/samples/%2e%2e/secret.jpg"])
async def test_keys_that_are_not_keyframe_images_are_never_forwarded_to_the_api(path: str) -> None:
    http = _http_with_jobs()
    async with _ui(http) as ui:
        response = await ui.get(path)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert not any("/images/" in probe.url for probe in http.gets)


async def test_an_image_the_api_does_not_have_is_not_found() -> None:
    class _Missing(FakeHttpClient):
        def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
            raise HttpStatusError(HTTPStatus.NOT_FOUND, "the API returned HTTP 404")

    async with _ui(_Missing()) as ui:
        response = await ui.get(f"/images/{KEY}")

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_an_unreachable_api_is_a_bad_gateway_not_a_crash() -> None:
    async with _ui(FakeHttpClient(error=RuntimeError("Cannot reach the API"))) as ui:
        response = await ui.get("/")

    assert response.status_code == HTTPStatus.BAD_GATEWAY
    assert "Cannot reach the API" in response.text


async def test_errors_use_the_same_json_envelope_as_the_api() -> None:
    async with _ui(_http_with_jobs()) as ui:
        response = await ui.get("/images/v1.0-mini/scene.json")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.headers["Content-Type"] == "application/json"
    assert response.json()["error"]["code"] == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"]["status"] == "Unprocessable Entity"


async def test_the_health_probe_never_calls_the_api() -> None:
    http = FakeHttpClient(error=RuntimeError("down"))
    async with _ui(http) as ui:
        response = await ui.get("/healthz")

    assert response.status_code == HTTPStatus.OK
    assert http.gets == []


async def test_unknown_paths_are_not_found_in_the_json_envelope() -> None:
    async with _ui(_http_with_jobs()) as ui:
        response = await ui.get("/etc/passwd")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["error"]["code"] == HTTPStatus.NOT_FOUND


async def test_without_an_api_there_is_no_image_route() -> None:
    async with _ui(None, all_jobs=False) as ui:
        response = await ui.get(f"/images/{KEY}")

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_result_files_in_the_output_directory_are_shown_without_an_api(tmp_path: Path) -> None:
    image = tmp_path / "a.jpg"
    image.write_bytes(b"jpeg bytes")
    (tmp_path / "model-a.json").write_text(json.dumps([{**_description("a result file"), "image_path": image.name}]))
    app = create_ui_app(make_settings(output_dir=str(tmp_path), nuscenes_dataroot=str(tmp_path)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ui") as ui:
        response = await ui.get("/")

    assert response.status_code == HTTPStatus.OK
    assert b"a result file" in response.content
    assert b"data:image" in response.content


async def test_starting_with_nothing_to_show_fails_fast(tmp_path: Path) -> None:
    app = create_ui_app(make_settings(output_dir=str(tmp_path)))

    with pytest.raises(ValueError, match="no result files"):
        async with app.router.lifespan_context(app):
            pass
