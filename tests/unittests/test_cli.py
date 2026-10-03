"""Only what needs no collaborators; each command's routing is covered by the integration tests."""

import pytest
from typer.testing import CliRunner

from backseat_driver import __version__
from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app

runner = CliRunner()


def test_version_flag_prints_the_package_version_and_exits() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"backseat-driver {__version__}"


def test_short_version_flag_matches_the_long_one() -> None:
    assert runner.invoke(app, ["-V"]).output == runner.invoke(app, ["--version"]).output


def test_help_lists_every_command_group() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("run", "test", "worker", "db"):
        assert command in result.output


@pytest.mark.parametrize("group", ["test", "worker", "db"])
def test_command_groups_show_help_when_called_without_a_subcommand(group: str) -> None:
    result = runner.invoke(app, [group])

    assert "Usage" in result.output


def test_unknown_command_is_a_usage_error() -> None:
    assert runner.invoke(app, ["nope"]).exit_code == 2
