"""`report` over real result files; `ui` is exercised by the Selenium tests, which run the real server."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.config import get_settings
from backseat_driver.models import SceneDescription

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def test_report_defaults_to_every_result_in_the_output_dir(output_dir: Path) -> None:
    result = runner.invoke(app, ["report"], env={"BACKSEAT_DRIVER_OUTPUT_DIR": str(output_dir)})

    assert result.exit_code == 0, result.output
    assert "wrote report for 2 description(s)" in result.output
    html = (output_dir / "report.html").read_text(encoding="utf-8")
    assert "model-a" in html
    assert "model-b" in html


def test_report_accepts_explicit_files_and_output(output_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "custom.html"

    result = runner.invoke(app, ["report", str(output_dir / "model-a.json"), "--output", str(target)])

    assert result.exit_code == 0, result.output
    assert "wrote report for 1 description(s)" in result.output
    assert "model-b" not in target.read_text(encoding="utf-8")


def test_report_without_results_fails_with_a_hint(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report"], env={"BACKSEAT_DRIVER_OUTPUT_DIR": str(tmp_path / "missing")})

    assert result.exit_code != 0
    assert "no result files found" in result.output
