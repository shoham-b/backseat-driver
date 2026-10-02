import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from backseat_driver import __version__
from backseat_driver.captioning import factory
from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.cli import db as db_cli
from backseat_driver.cli import run as run_cli
from backseat_driver.cli import test as test_cli
from backseat_driver.cli import worker as worker_cli
from backseat_driver.config import get_settings
from backseat_driver.jobs import postgres_job_store
from backseat_driver.scenes import nuscenes_scene_loader
from tests.fakes import FakeCaptioner, FakeSceneLoader, make_keyframe

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_global_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Commands call `setup_logging`, which replaces loguru's sinks process-wide; keep that out of other tests."""
    for module in (run_cli, db_cli, worker_cli):
        monkeypatch.setattr(module, "setup_logging", mock.Mock())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


# --- run -----------------------------------------------------------------------------------------------------------


@pytest.fixture
def pipeline_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, mock.Mock]:
    loader_cls = mock.Mock(return_value=FakeSceneLoader([make_keyframe(1), make_keyframe(2), make_keyframe(3)]))
    build = mock.Mock(return_value=FakeCaptioner("a quiet street"))
    monkeypatch.setattr(nuscenes_scene_loader, "NuScenesSceneLoader", loader_cls)
    monkeypatch.setattr(factory, "build_captioner", build)
    return {"loader_cls": loader_cls, "build": build}


def test_run_writes_one_json_entry_per_scene_and_echoes_them(
    tmp_path: Path, pipeline_doubles: dict[str, mock.Mock]
) -> None:
    output = tmp_path / "out" / "descriptions.json"

    result = runner.invoke(app, ["run", "--output", str(output)])

    assert result.exit_code == 0, result.output
    written = json.loads(output.read_text(encoding="utf-8"))
    assert [d["scene_name"] for d in written] == ["scene-0001", "scene-0002", "scene-0003"]
    assert "Wrote 3 scene description(s)" in result.output
    assert "scene-0002: a quiet street" in result.output


def test_run_defaults_come_from_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_doubles: dict[str, mock.Mock]
) -> None:
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_DATAROOT", "/env/root")
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_VERSION", "v-env")
    monkeypatch.setenv("BACKSEAT_DRIVER_CAMERA_CHANNEL", "CAM_ENV")
    monkeypatch.setenv("BACKSEAT_DRIVER_OUTPUT_PATH", str(tmp_path / "env.json"))

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    pipeline_doubles["loader_cls"].assert_called_once_with(
        dataroot="/env/root", version="v-env", camera_channel="CAM_ENV"
    )
    assert (tmp_path / "env.json").exists()


def test_run_options_override_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pipeline_doubles: dict[str, mock.Mock]
) -> None:
    monkeypatch.setenv("BACKSEAT_DRIVER_NUSCENES_DATAROOT", "/env/root")

    result = runner.invoke(
        app,
        [
            "run",
            "--dataroot", "/cli/root",
            "--version", "v-cli",
            "--camera", "CAM_BACK",
            "--backend", "ollama",
            "--model", "llava:7b",
            "--output", str(tmp_path / "o.json"),
        ],
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    pipeline_doubles["loader_cls"].assert_called_once_with(
        dataroot="/cli/root", version="v-cli", camera_channel="CAM_BACK"
    )
    [(settings,), kwargs] = pipeline_doubles["build"].call_args
    assert kwargs == {"backend": "ollama", "model_name": "llava:7b"}
    assert settings.nuscenes_dataroot == "/env/root"


def test_run_max_scenes_limits_the_work(tmp_path: Path, pipeline_doubles: dict[str, mock.Mock]) -> None:
    output = tmp_path / "o.json"

    result = runner.invoke(app, ["run", "--max-scenes", "2", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text(encoding="utf-8"))) == 2


def test_run_on_an_empty_dataset_writes_an_empty_array(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nuscenes_scene_loader, "NuScenesSceneLoader", mock.Mock(return_value=FakeSceneLoader([])))
    monkeypatch.setattr(factory, "build_captioner", mock.Mock(return_value=FakeCaptioner()))
    output = tmp_path / "o.json"

    result = runner.invoke(app, ["run", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8")) == []
    assert "Wrote 0 scene description(s)" in result.output


def test_run_rejects_an_unknown_backend_before_doing_any_work(pipeline_doubles: dict[str, mock.Mock]) -> None:
    result = runner.invoke(app, ["run", "--backend", "bogus"])

    assert result.exit_code == 2
    pipeline_doubles["loader_cls"].assert_not_called()


def test_run_rejects_a_non_integer_max_scenes() -> None:
    assert runner.invoke(app, ["run", "--max-scenes", "many"]).exit_code == 2


def test_run_surfaces_a_failing_captioner_rather_than_writing_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captioner = mock.Mock(model_name="m")
    captioner.caption.side_effect = RuntimeError("model exploded")
    monkeypatch.setattr(
        nuscenes_scene_loader, "NuScenesSceneLoader", mock.Mock(return_value=FakeSceneLoader([make_keyframe(1)]))
    )
    monkeypatch.setattr(factory, "build_captioner", mock.Mock(return_value=captioner))
    output = tmp_path / "o.json"

    result = runner.invoke(app, ["run", "--output", str(output)])

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert not output.exists()


# --- db ------------------------------------------------------------------------------------------------------------


def test_db_init_creates_the_schema_in_the_configured_database(monkeypatch: pytest.MonkeyPatch) -> None:
    store_cls = mock.Mock()
    monkeypatch.setattr(postgres_job_store, "PostgresJobStore", store_cls)
    monkeypatch.setenv("BACKSEAT_DRIVER_DATABASE_URL", "postgresql+psycopg://db/x")

    result = runner.invoke(app, ["db", "init"])

    assert result.exit_code == 0, result.output
    store_cls.assert_called_once_with("postgresql+psycopg://db/x")
    store_cls.return_value.ensure_schema.assert_called_once_with()


def test_db_init_fails_loudly_when_the_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    store_cls = mock.Mock()
    store_cls.return_value.ensure_schema.side_effect = ConnectionError("no route to host")
    monkeypatch.setattr(postgres_job_store, "PostgresJobStore", store_cls)

    result = runner.invoke(app, ["db", "init"])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConnectionError)


# --- worker --------------------------------------------------------------------------------------------------------


def test_ingest_worker_consumes_only_the_ingest_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    from backseat_driver import tasks
    from backseat_driver.jobs.celery_job_queue import INGEST_QUEUE

    worker_main = mock.Mock()
    monkeypatch.setattr(tasks.celery_app, "worker_main", worker_main)

    result = runner.invoke(app, ["worker", "ingest"])

    assert result.exit_code == 0, result.output
    [argv] = worker_main.call_args.args
    assert argv[argv.index("-Q") + 1] == INGEST_QUEUE
    assert "--pool=solo" in argv
    assert {"--without-gossip", "--without-mingle", "--without-heartbeat"} <= set(argv)


def test_caption_worker_loads_the_model_before_it_starts_consuming(monkeypatch: pytest.MonkeyPatch) -> None:
    from backseat_driver import tasks
    from backseat_driver.jobs.celery_job_queue import CAPTION_QUEUE

    order: list[str] = []
    monkeypatch.setattr(tasks, "caption_worker", lambda: order.append("load"))
    monkeypatch.setattr(tasks.celery_app, "worker_main", lambda argv: order.append(argv[argv.index("-Q") + 1]))

    result = runner.invoke(app, ["worker", "caption"])

    assert result.exit_code == 0, result.output
    assert order == ["load", CAPTION_QUEUE]


def test_caption_worker_does_not_start_consuming_when_the_model_cannot_load(monkeypatch: pytest.MonkeyPatch) -> None:
    from backseat_driver import tasks

    worker_main = mock.Mock()
    monkeypatch.setattr(tasks.celery_app, "worker_main", worker_main)
    monkeypatch.setattr(tasks, "caption_worker", mock.Mock(side_effect=RuntimeError("cannot load model")))

    result = runner.invoke(app, ["worker", "caption"])

    assert result.exit_code == 1
    worker_main.assert_not_called()


# --- test smoke ----------------------------------------------------------------------------------------------------


def test_smoke_runs_the_smoketests_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    main = mock.Mock(return_value=pytest.ExitCode.OK)
    monkeypatch.setattr(pytest, "main", main)

    result = runner.invoke(app, ["test", "smoke"])

    assert result.exit_code == 0, result.output
    [args] = main.call_args.args
    assert args == [str(test_cli._PROJECT_ROOT / "tests" / "smoketests")]
    assert (test_cli._PROJECT_ROOT / "tests" / "smoketests").is_dir()


def test_smoke_verbose_is_forwarded_to_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    main = mock.Mock(return_value=pytest.ExitCode.OK)
    monkeypatch.setattr(pytest, "main", main)

    runner.invoke(app, ["test", "smoke", "--verbose"])

    assert "-v" in main.call_args.args[0]


def test_smoke_api_url_option_is_exported_for_the_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_URL", "http://before")  # so monkeypatch restores it after the command overwrites it
    monkeypatch.setattr(pytest, "main", mock.Mock(return_value=pytest.ExitCode.OK))

    runner.invoke(app, ["test", "smoke", "--api-url", "http://svc:9"])

    assert os.environ["API_URL"] == "http://svc:9"


def test_smoke_api_url_falls_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_URL", "http://from-env:1")
    monkeypatch.setattr(pytest, "main", mock.Mock(return_value=pytest.ExitCode.OK))

    result = runner.invoke(app, ["test", "smoke"])

    assert result.exit_code == 0, result.output


def test_smoke_treats_no_collected_tests_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pytest, "main", mock.Mock(return_value=pytest.ExitCode.NO_TESTS_COLLECTED))

    assert runner.invoke(app, ["test", "smoke"]).exit_code == 0


@pytest.mark.parametrize(
    "code", [pytest.ExitCode.TESTS_FAILED, pytest.ExitCode.INTERNAL_ERROR, pytest.ExitCode.USAGE_ERROR]
)
def test_smoke_propagates_a_failing_pytest_exit_code(monkeypatch: pytest.MonkeyPatch, code: pytest.ExitCode) -> None:
    monkeypatch.setattr(pytest, "main", mock.Mock(return_value=code))

    assert runner.invoke(app, ["test", "smoke"]).exit_code == int(code)


def test_smoke_explains_how_to_install_pytest_when_it_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pytest", None)  # makes `import pytest` raise ImportError

    result = runner.invoke(app, ["test", "smoke"])

    assert result.exit_code == 1
    assert "uv sync --group dev" in result.output
