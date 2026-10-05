from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app

runner = CliRunner()


def test_upload_rejects_a_camera_together_with_all_cameras() -> None:
    result = runner.invoke(app, ["dataset", "upload", "--camera", "back", "--all-cameras"])

    assert result.exit_code == 2
    assert "--all-cameras" in result.output


def test_upload_requires_a_dataset_bucket() -> None:
    result = runner.invoke(app, ["dataset", "upload"], env={"BACKSEAT_DRIVER_DATASET_BUCKET": ""})

    assert result.exit_code != 0
    assert "No dataset bucket chosen" in str(result.exception)
