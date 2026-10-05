"""`report --job`: the report is built from the API alone, with a stub API on localhost standing in for the real one."""

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path

from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from tests.stub_server import Received, Reply, Responder, StubServer, json_reply

runner = CliRunner()
JOB_ID = "6f1c0a52-0b6f-4c63-bb7f-8d5a2d0c4e11"
KEY = "samples/CAM_FRONT/a.jpg"
DESCRIPTION = {
    "scene_token": "t",
    "scene_name": "scene-0001",
    "camera_channel": "CAM_FRONT",
    "image_path": KEY,
    "description": "a parked truck",
    "model_name": "stub-model",
    "reference_description": "Parked truck",
}


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


def _api(state: str) -> Responder:
    def respond(received: Received) -> Reply:
        routes = {
            f"/jobs/{JOB_ID}": json_reply(_job(state)),
            f"/jobs/{JOB_ID}/descriptions": json_reply([DESCRIPTION]),
            f"/images/{KEY}": Reply(HTTPStatus.OK, b"jpeg bytes", "image/jpeg"),
        }
        return routes.get(received.path, json_reply({}, HTTPStatus.NOT_FOUND))

    return respond


def test_a_report_is_built_from_a_job_with_its_images_inlined_from_the_api(
    stub_server: Callable[[Responder], StubServer], tmp_path: Path
) -> None:
    api = stub_server(_api("completed"))
    output = tmp_path / "report.html"

    result = runner.invoke(app, ["report", "--job", JOB_ID, "--api-url", api.url, "--output", str(output)])

    html = output.read_text()
    assert result.exit_code == 0, result.output
    assert "a parked truck" in html
    assert "stub-model" in html
    assert "data:image/jpeg;base64," in html  # the image came over HTTP, not from a dataset on disk


def test_a_job_that_is_still_running_fails_the_report(
    stub_server: Callable[[Responder], StubServer], tmp_path: Path
) -> None:
    api = stub_server(_api("running"))
    output = tmp_path / "report.html"

    result = runner.invoke(app, ["report", "--job", JOB_ID, "--api-url", api.url, "--output", str(output)])

    assert result.exit_code != 0
    assert "running" in str(result.exception)
    assert not output.exists()
