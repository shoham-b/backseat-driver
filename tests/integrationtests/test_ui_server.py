"""The report UI server over real HTTP with a fake API behind it: pages are rebuilt per load, images proxied."""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from uuid import uuid4

import pytest

from backseat_driver.captioning.http_client import HttpResponse
from backseat_driver.errors import HttpStatusError
from backseat_driver.reporting.api_source import ApiReportSource
from backseat_driver.reporting.ui_server import ReportPage, make_handler
from tests.fakes import FakeHttpClient

API = "http://api"
KEY = "samples/CAM_FRONT/a.jpg"


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


class _Running:
    def __init__(self, http: FakeHttpClient, all_jobs: bool = True) -> None:
        source = ApiReportSource(API, http)
        page = ReportPage([], source, [], all_jobs, live_api_url="http://localhost:8080")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(page, source))
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def get(self, path: str) -> tuple[int, bytes, dict[str, str]]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _http_with_jobs(*jobs: tuple[str, list[dict[str, object]]]) -> FakeHttpClient:
    http = FakeHttpClient()
    http.responses_by_url = {
        f"{API}/jobs?state=completed&limit=500": _json([_job(job_id) for job_id, _ in jobs]),
        f"{API}/images/{KEY}": HttpResponse(b"jpeg bytes", "image/jpeg"),
        **{f"{API}/jobs/{job_id}/descriptions": _json(items) for job_id, items in jobs},
    }
    return http


@pytest.fixture
def running() -> Iterator[list[_Running]]:
    started: list[_Running] = []
    yield started
    for server in started:
        server.stop()


def _start(running: list[_Running], http: FakeHttpClient, all_jobs: bool = True) -> _Running:
    running.append(_Running(http, all_jobs))
    return running[-1]


def test_the_page_shows_the_completed_jobs_and_points_images_at_the_ui_itself(running: list[_Running]) -> None:
    ui = _start(running, _http_with_jobs((str(uuid4()), [_description("a parked truck")])))

    status, body, headers = ui.get("/")

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"a parked truck" in body
    assert b"/images/samples/CAM_FRONT/a.jpg" in body
    assert b"data:image" not in body


def test_a_job_finished_after_startup_shows_up_on_the_next_load(running: list[_Running]) -> None:
    http = _http_with_jobs((str(uuid4()), [_description("first job")]))
    ui = _start(running, http)
    assert b"second job" not in ui.get("/")[1]
    second = str(uuid4())
    http.responses_by_url[f"{API}/jobs?state=completed&limit=500"] = _json([_job(second)])
    http.responses_by_url[f"{API}/jobs/{second}/descriptions"] = _json([_description("second job")])

    body = ui.get("/")[1]

    assert b"second job" in body


def test_several_jobs_of_one_model_show_only_the_newest(running: list[_Running]) -> None:
    newest, older = str(uuid4()), str(uuid4())
    ui = _start(
        running,
        _http_with_jobs((newest, [_description("new words")]), (older, [_description("old words")])),
    )

    body = ui.get("/")[1]

    assert b"new words" in body
    assert b"old words" not in body


def test_an_image_is_proxied_from_the_api_with_caching_headers(running: list[_Running]) -> None:
    ui = _start(running, _http_with_jobs())

    status, body, headers = ui.get(f"/images/{KEY}")

    assert (status, body, headers["Content-Type"]) == (200, b"jpeg bytes", "image/jpeg")
    assert "immutable" in headers["Cache-Control"]


@pytest.mark.parametrize("path", ["/images/v1.0-mini/scene.json", "/images/samples/%2e%2e/secret.jpg"])
def test_keys_that_are_not_keyframe_images_are_never_forwarded_to_the_api(running: list[_Running], path: str) -> None:
    http = _http_with_jobs()
    ui = _start(running, http)

    status, _, _ = ui.get(path)

    assert status == 422
    assert not any("/images/" in probe.url for probe in http.gets)


def test_an_image_the_api_does_not_have_is_not_found(running: list[_Running]) -> None:
    http = _http_with_jobs()
    del http.responses_by_url[f"{API}/images/{KEY}"]

    class _Missing(FakeHttpClient):
        def get(self, url: str, headers: dict[str, str], timeout: float, service: str) -> HttpResponse:
            raise HttpStatusError(404, "the API returned HTTP 404")

    ui = _start(running, _Missing())

    assert ui.get(f"/images/{KEY}")[0] == 404


def test_an_unreachable_api_is_a_bad_gateway_not_a_crash(running: list[_Running]) -> None:
    ui = _start(running, FakeHttpClient(error=RuntimeError("Cannot reach the API")))

    status, body, _ = ui.get("/")

    assert status == 502
    assert b"Cannot reach the API" in body


def test_errors_use_the_same_json_envelope_as_the_api(running: list[_Running]) -> None:
    ui = _start(running, _http_with_jobs())

    status, body, headers = ui.get("/images/v1.0-mini/scene.json")

    assert (status, headers["Content-Type"]) == (422, "application/json")
    assert json.loads(body)["error"]["code"] == 422
    assert json.loads(body)["error"]["status"] == "Unprocessable Entity"


def test_the_health_probe_never_calls_the_api(running: list[_Running]) -> None:
    http = FakeHttpClient(error=RuntimeError("down"))
    ui = _start(running, http)

    assert ui.get("/healthz")[0] == 200
    assert http.gets == []


def test_unknown_paths_are_not_found(running: list[_Running]) -> None:
    assert _start(running, _http_with_jobs()).get("/etc/passwd")[0] == 404
