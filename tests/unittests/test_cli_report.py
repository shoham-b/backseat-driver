from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.cli import report as report_cli
from backseat_driver.config import get_settings
from backseat_driver.models import SceneDescription

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
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
    monkeypatch.setenv("BACKSEAT_DRIVER_OUTPUT_DIR", str(directory))
    return directory


def test_report_defaults_to_every_result_in_the_output_dir(output_dir: Path) -> None:
    result = runner.invoke(app, ["report"])

    assert result.exit_code == 0, result.output
    assert "Wrote report for 2 description(s)" in result.output
    html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert "model-a" in html
    assert "model-b" in html


def test_report_accepts_explicit_files_and_output(output_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "custom.html"

    result = runner.invoke(app, ["report", str(output_dir / "model-a.json"), "--output", str(target)])

    assert result.exit_code == 0, result.output
    assert "Wrote report for 1 description(s)" in result.output
    assert "model-b" not in target.read_text(encoding="utf-8")


def test_report_without_results_fails_with_a_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BACKSEAT_DRIVER_OUTPUT_DIR", str(tmp_path / "missing"))

    result = runner.invoke(app, ["report"])

    assert result.exit_code != 0
    assert "no result files found" in result.output


def test_ui_serves_the_report_and_opens_the_browser(output_dir: Path) -> None:
    server = mock.MagicMock()
    server.__enter__.return_value = server
    server.serve_forever.side_effect = KeyboardInterrupt

    with (
        mock.patch.object(report_cli.http.server, "ThreadingHTTPServer", return_value=server) as server_cls,
        mock.patch.object(report_cli.webbrowser, "open") as open_browser,
    ):
        result = runner.invoke(app, ["ui", "--port", "9999"])

    assert result.exit_code == 0, result.output
    assert server_cls.call_args.args[0] == ("127.0.0.1", 9999)
    open_browser.assert_called_once_with("http://127.0.0.1:9999/")
    assert "Serving 2 description(s) from 2 file(s)" in result.output
    assert "Stopped" in result.output


def test_ui_no_open_leaves_the_browser_alone(output_dir: Path) -> None:
    server = mock.MagicMock()
    server.__enter__.return_value = server
    server.serve_forever.side_effect = KeyboardInterrupt

    with (
        mock.patch.object(report_cli.http.server, "ThreadingHTTPServer", return_value=server),
        mock.patch.object(report_cli.webbrowser, "open") as open_browser,
    ):
        result = runner.invoke(app, ["ui", "--no-open"])

    assert result.exit_code == 0, result.output
    open_browser.assert_not_called()
