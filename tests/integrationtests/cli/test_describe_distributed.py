"""`describe --mode distributed`: the command submits a job to the API and writes what the workers produced.

A stub API on localhost stands in for the API and its workers, which have their own tests; what is under test here is
the command: where it sends the job, what it waits for, and the file it writes.
"""

import json
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path

from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from tests.stub_server import Received, Reply, Responder, StubServer, json_reply

runner = CliRunner()
JOB_ID = "6f1c0a52-0b6f-4c63-bb7f-8d5a2d0c4e11"
DESCRIPTION = {
    "scene_token": "t",
    "scene_name": "scene-0001",
    "camera_channel": "CAM_FRONT",
    "image_path": "samples/CAM_FRONT/a.jpg",
    "description": "a parked truck",
    "model_name": "worker-model",
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
        **({"error": "caption failed: boom"} if state == "failed" else {}),
    }


def _api_whose_job_ends(final_state: str) -> Responder:
    """Accepts a job, then reports it in `final_state`."""

    def respond(received: Received) -> Reply:
        if received.method == "POST":
            return json_reply(_job("pending"), HTTPStatus.ACCEPTED)
        if received.path == f"/jobs/{JOB_ID}":
            return json_reply(_job(final_state))
        if received.path == f"/jobs/{JOB_ID}/descriptions":
            return json_reply([DESCRIPTION])
        return json_reply({}, HTTPStatus.NOT_FOUND)

    return respond


def test_the_job_the_workers_finish_is_written_to_the_output_file(
    stub_server: Callable[[Responder], StubServer], tmp_path: Path
) -> None:
    api = stub_server(_api_whose_job_ends("completed"))
    output = tmp_path / "result.json"
    args = ["describe", "--mode", "distributed", "--api-url", api.url, "--max-scenes", "3"]

    result = runner.invoke(app, [*args, "--output", str(output)])
    written = json.loads(output.read_text())

    assert result.exit_code == 0, result.output
    assert [request.json() for request in api.requests if request.method == "POST"] == [{"max_scenes": 3}]
    assert [(d["scene_name"], d["description"], d["model_name"]) for d in written] == [
        ("scene-0001", "a parked truck", "worker-model")
    ]
    assert "scene-0001 [CAM_FRONT]: a parked truck" in result.output


def test_a_failed_job_fails_the_command_and_writes_nothing(
    stub_server: Callable[[Responder], StubServer], tmp_path: Path
) -> None:
    api = stub_server(_api_whose_job_ends("failed"))
    output = tmp_path / "result.json"

    result = runner.invoke(app, ["describe", "--mode", "distributed", "--api-url", api.url, "--output", str(output)])

    assert result.exit_code != 0
    assert "caption failed: boom" in str(result.exception)
    assert not output.exists()
