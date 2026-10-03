from pathlib import Path

import pytest
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.cli.context import CliContext
from backseat_driver.models import SceneDescription
from tests.fakes import FakeServer, make_cli_context, make_settings

runner = CliRunner()


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"\xff\xd8fake")
    directory = tmp_path / "out"
    directory.mkdir()
    for model in ("model-a", "model-b"):
        descriptions = [
            SceneDescription(
                scene_token="token-1",
                scene_name="scene-0001",
                camera_channel="CAM_FRONT",
                image_path=str(image),
                description="a parked truck",
                model_name=model,
                reference_description="Parked truck",
            )
        ]
        payload = "[" + ",".join(d.model_dump_json() for d in descriptions) + "]"
        (directory / f"{model}.json").write_text(payload, encoding="utf-8")
    return directory


def _context(output_dir: Path, server: FakeServer | None = None, **settings: str | int) -> CliContext:
    return make_cli_context(
        settings=make_settings(output_dir=str(output_dir), **settings), serve=server or FakeServer()
    )


def test_report_defaults_to_every_result_in_the_output_dir(output_dir: Path) -> None:
    result = runner.invoke(app, ["report"], obj=_context(output_dir))

    assert result.exit_code == 0, result.output
    assert "Wrote report for 2 description(s)" in result.output
    html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert "model-a" in html
    assert "model-b" in html


def test_report_accepts_explicit_files_and_output(output_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "custom.html"

    result = runner.invoke(
        app,
        ["report", str(output_dir / "model-a.json"), "--output", str(target)],
        obj=_context(output_dir),
    )

    assert result.exit_code == 0, result.output
    assert "Wrote report for 1 description(s)" in result.output
    assert "model-b" not in target.read_text(encoding="utf-8")


def test_report_without_results_fails_with_a_hint(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report"], obj=_context(tmp_path / "missing"))

    assert result.exit_code != 0
    assert "no result files found" in result.output


def test_ui_serves_the_report_and_opens_the_browser(output_dir: Path) -> None:
    server = FakeServer()

    result = runner.invoke(app, ["ui", "--port", "9999"], obj=_context(output_dir, server))

    assert result.exit_code == 0, result.output
    assert server.calls == [("127.0.0.1", 9999, "http://127.0.0.1:9999/")]
    assert "model-a" in server.html
    assert "Serving 2 description(s) from 2 file(s)" in result.output
    assert "Stopped" in result.output


def test_ui_points_the_live_card_at_the_configured_api(output_dir: Path) -> None:
    server = FakeServer()

    result = runner.invoke(app, ["ui", "--no-open", "--api-url", "http://api:9"], obj=_context(output_dir, server))

    assert result.exit_code == 0, result.output
    assert '"api_url": "http://api:9"' in server.html


def test_ui_defaults_the_live_card_to_the_settings_api_url(output_dir: Path) -> None:
    server = FakeServer()

    runner.invoke(app, ["ui", "--no-open"], obj=_context(output_dir, server))

    assert '"api_url": "http://127.0.0.1:8080"' in server.html


def test_ui_no_open_leaves_the_browser_alone(output_dir: Path) -> None:
    server = FakeServer()

    result = runner.invoke(app, ["ui", "--no-open"], obj=_context(output_dir, server))

    assert result.exit_code == 0, result.output
    assert [open_url for _, _, open_url in server.calls] == [None]


def test_ui_takes_host_and_port_from_the_settings_when_no_flags_are_given(output_dir: Path) -> None:
    server = FakeServer()

    result = runner.invoke(app, ["ui", "--no-open"], obj=_context(output_dir, server, ui_host="0.0.0.0", ui_port=9123))

    assert result.exit_code == 0, result.output
    assert [(host, port) for host, port, _ in server.calls] == [("0.0.0.0", 9123)]
    assert "http://0.0.0.0:9123/" in result.output


def test_ui_flags_override_the_settings(output_dir: Path) -> None:
    server = FakeServer()

    runner.invoke(
        app,
        ["ui", "--no-open", "--host", "10.0.0.5", "--port", "7000"],
        obj=_context(output_dir, server, ui_port=9123),
    )

    assert [(host, port) for host, port, _ in server.calls] == [("10.0.0.5", 7000)]
