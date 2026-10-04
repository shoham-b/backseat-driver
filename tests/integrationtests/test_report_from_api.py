"""`report --job`: the report is built from the API alone, with a stub API on localhost standing in for the real one."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.config import get_settings

runner = CliRunner()
JOB_ID = "6f1c0a52-0b6f-4c63-bb7f-8d5a2d0c4e11"
KEY = "samples/CAM_FRONT/a.jpg"


def _job(state: str) -> dict[str, object]:
    return {
        "job_id": JOB_ID,
        "transaction_id": "tx",
        "state": state,
        "max_scenes": None,
        "expected_scenes": 1,
        "completed_scenes": 1 if state == "completed" else 0,
        "created_at": "2026-01-01T00:00:00Z",
    }


DESCRIPTION = {
    "scene_token": "t",
    "scene_name": "scene-0001",
    "camera_channel": "CAM_FRONT",
    "image_path": KEY,
    "description": "a parked truck",
    "model_name": "stub-model",
    "reference_description": "Parked truck",
}


def _serve(state: str) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            routes = {
                f"/jobs/{JOB_ID}": (json.dumps(_job(state)).encode(), "application/json"),
                f"/jobs/{JOB_ID}/descriptions": (json.dumps([DESCRIPTION]).encode(), "application/json"),
                f"/images/{KEY}": (b"jpeg bytes", "image/jpeg"),
            }
            body, content_type = routes.get(self.path, (b"{}", "application/json"))
            self.send_response(200 if self.path in routes else 404)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def completed_api() -> Iterator[str]:
    yield from _serve("completed")


@pytest.fixture
def running_api() -> Iterator[str]:
    yield from _serve("running")


def test_a_report_is_built_from_a_job_with_its_images_inlined_from_the_api(completed_api: str, tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    result = runner.invoke(app, ["report", "--job", JOB_ID, "--api-url", completed_api, "--output", str(output)])

    html = output.read_text()
    assert result.exit_code == 0, result.output
    assert "a parked truck" in html
    assert "stub-model" in html
    assert "data:image/jpeg;base64," in html  # the image came over HTTP, not from a dataset on disk


def test_a_job_that_is_still_running_fails_the_report(running_api: str, tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    result = runner.invoke(app, ["report", "--job", JOB_ID, "--api-url", running_api, "--output", str(output)])

    assert result.exit_code != 0
    assert "running" in str(result.exception)
    assert not output.exists()
