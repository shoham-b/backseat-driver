import json
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from backseat_driver import __version__
from backseat_driver.captioning.captioner import Captioner
from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.cli import test as test_cli
from backseat_driver.cli.context import CliContext, PytestNotInstalledError, default_context
from backseat_driver.jobs.celery_job_queue import CAPTION_QUEUE, INGEST_QUEUE
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.scenes.nuscenes_dataset import NuScenesDatasetCache
from tests.fakes import (
    FakeCaptioner,
    FakeCaptionerFactory,
    FakeDatasetCache,
    FakeLoaderFactory,
    FakeLogging,
    FakePytestRunner,
    FakeSchemaInit,
    FakeWorkerHost,
    make_cli_context,
    make_keyframe,
    make_settings,
)

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


def test_the_default_context_wires_the_real_adapters_without_connecting() -> None:
    context = default_context()

    assert isinstance(context.dataset_cache, NuScenesDatasetCache)
    assert context.configure_logging is setup_logging


# --- run -----------------------------------------------------------------------------------------------------------


@dataclass
class RunDoubles:
    cache: FakeDatasetCache
    loaders: FakeLoaderFactory
    captioners: FakeCaptionerFactory
    logging: FakeLogging

    def context(self, **settings: str) -> CliContext:
        return make_cli_context(
            settings=make_settings(**settings),
            configure_logging=self.logging,
            dataset_cache=self.cache,
            build_loader=self.loaders,
            build_captioner=self.captioners,
        )


def _doubles(keyframes: int = 3, captioner: Captioner | None = None) -> RunDoubles:
    return RunDoubles(
        FakeDatasetCache(),
        FakeLoaderFactory([make_keyframe(n) for n in range(1, keyframes + 1)]),
        FakeCaptionerFactory(captioner or FakeCaptioner("a quiet street")),
        FakeLogging(),
    )


def test_run_writes_one_json_entry_per_scene_and_echoes_them(tmp_path: Path) -> None:
    output = tmp_path / "out" / "descriptions.json"

    result = runner.invoke(app, ["run", "--output", str(output)], obj=_doubles().context())

    assert result.exit_code == 0, result.output
    written = json.loads(output.read_text(encoding="utf-8"))
    assert [d["scene_name"] for d in written] == ["scene-0001", "scene-0002", "scene-0003"]
    assert "Wrote 3 scene description(s)" in result.output
    assert "scene-0002: a quiet street" in result.output


def test_run_configures_logging_from_the_settings(tmp_path: Path) -> None:
    doubles = _doubles(keyframes=0)

    runner.invoke(app, ["run", "--output", str(tmp_path / "o.json")], obj=doubles.context(log_format="json"))

    assert doubles.logging.calls == [(LogFormat.JSON, "cli")]


def test_run_defaults_come_from_settings(tmp_path: Path) -> None:
    doubles = _doubles()
    context = doubles.context(
        nuscenes_dataroot="/env/root", nuscenes_version="v-env", camera_channel="CAM_ENV", output_dir=str(tmp_path)
    )

    result = runner.invoke(app, ["run"], obj=context)

    assert result.exit_code == 0, result.output
    assert doubles.cache.ensured == [("/env/root", "v-env")]
    assert doubles.loaders.calls == [("/env/root", "v-env", "CAM_ENV")]
    assert (tmp_path / "huggingface__Salesforce-blip-image-captioning-base.json").exists()


def test_run_options_override_settings(tmp_path: Path) -> None:
    doubles = _doubles()

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
        obj=doubles.context(nuscenes_dataroot="/env/root"),
    )  # fmt: skip

    assert result.exit_code == 0, result.output
    assert doubles.cache.ensured == [("/cli/root", "v-cli")]
    assert doubles.loaders.calls == [("/cli/root", "v-cli", "CAM_BACK")]
    [(settings, backend, model)] = doubles.captioners.calls
    assert (backend, model) == ("ollama", "llava:7b")
    assert settings.nuscenes_dataroot == "/env/root"


def test_run_max_scenes_limits_the_work(tmp_path: Path) -> None:
    output = tmp_path / "o.json"

    result = runner.invoke(app, ["run", "--max-scenes", "2", "--output", str(output)], obj=_doubles().context())

    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text(encoding="utf-8"))) == 2


def test_run_on_an_empty_dataset_writes_an_empty_array(tmp_path: Path) -> None:
    output = tmp_path / "o.json"

    result = runner.invoke(app, ["run", "--output", str(output)], obj=_doubles(keyframes=0).context())

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8")) == []
    assert "Wrote 0 scene description(s)" in result.output


def test_run_rejects_an_unknown_backend_before_doing_any_work() -> None:
    doubles = _doubles()

    result = runner.invoke(app, ["run", "--backend", "bogus"], obj=doubles.context())

    assert result.exit_code == 2
    assert doubles.cache.ensured == []
    assert doubles.loaders.calls == []


def test_run_rejects_a_non_integer_max_scenes() -> None:
    assert runner.invoke(app, ["run", "--max-scenes", "many"], obj=_doubles().context()).exit_code == 2


def test_run_surfaces_a_failing_captioner_rather_than_writing_partial_output(tmp_path: Path) -> None:
    captioner = mock.Mock(model_name="m")
    captioner.caption.side_effect = RuntimeError("model exploded")
    output = tmp_path / "o.json"

    result = runner.invoke(
        app, ["run", "--output", str(output)], obj=_doubles(keyframes=1, captioner=captioner).context()
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert not output.exists()


# --- db ------------------------------------------------------------------------------------------------------------


def test_db_init_creates_the_schema_in_the_configured_database() -> None:
    schema = FakeSchemaInit()
    context = make_cli_context(settings=make_settings(database_url="postgresql+psycopg://db/x"), init_schema=schema)

    result = runner.invoke(app, ["db", "init"], obj=context)

    assert result.exit_code == 0, result.output
    assert schema.urls == ["postgresql+psycopg://db/x"]


def test_db_init_fails_loudly_when_the_database_is_unreachable() -> None:
    context = make_cli_context(init_schema=FakeSchemaInit(error=ConnectionError("no route to host")))

    result = runner.invoke(app, ["db", "init"], obj=context)

    assert result.exit_code == 1
    assert isinstance(result.exception, ConnectionError)


# --- worker --------------------------------------------------------------------------------------------------------


def test_ingest_worker_consumes_only_the_ingest_queue() -> None:
    worker = FakeWorkerHost()
    context = make_cli_context(load_caption_model=worker.load_model, start_worker=worker.start)

    result = runner.invoke(app, ["worker", "ingest"], obj=context)

    assert result.exit_code == 0, result.output
    assert worker.events == [INGEST_QUEUE]
    assert "--pool=solo" in worker.argv
    assert {"--without-gossip", "--without-mingle", "--without-heartbeat"} <= set(worker.argv)


def test_caption_worker_loads_the_model_before_it_starts_consuming() -> None:
    worker = FakeWorkerHost()
    context = make_cli_context(load_caption_model=worker.load_model, start_worker=worker.start)

    result = runner.invoke(app, ["worker", "caption"], obj=context)

    assert result.exit_code == 0, result.output
    assert worker.events == ["load", CAPTION_QUEUE]


def test_caption_worker_does_not_start_consuming_when_the_model_cannot_load() -> None:
    worker = FakeWorkerHost(load_error=RuntimeError("cannot load model"))
    context = make_cli_context(load_caption_model=worker.load_model, start_worker=worker.start)

    result = runner.invoke(app, ["worker", "caption"], obj=context)

    assert result.exit_code == 1
    assert worker.events == []


# --- test smoke ----------------------------------------------------------------------------------------------------


def test_smoke_runs_the_smoketests_directory() -> None:
    pytest_runner = FakePytestRunner()

    result = runner.invoke(app, ["test", "smoke"], obj=make_cli_context(run_pytest=pytest_runner))

    assert result.exit_code == 0, result.output
    assert pytest_runner.calls == [([str(test_cli._PROJECT_ROOT / "tests" / "smoketests")], None)]
    assert (test_cli._PROJECT_ROOT / "tests" / "smoketests").is_dir()


def test_smoke_verbose_is_forwarded_to_pytest() -> None:
    pytest_runner = FakePytestRunner()

    runner.invoke(app, ["test", "smoke", "--verbose"], obj=make_cli_context(run_pytest=pytest_runner))

    assert "-v" in pytest_runner.calls[0][0]


def test_smoke_api_url_option_is_handed_to_the_runner() -> None:
    pytest_runner = FakePytestRunner()

    runner.invoke(app, ["test", "smoke", "--api-url", "http://svc:9"], obj=make_cli_context(run_pytest=pytest_runner))

    assert pytest_runner.calls[0][1] == "http://svc:9"


def test_smoke_api_url_falls_back_to_the_environment() -> None:
    pytest_runner = FakePytestRunner()

    result = runner.invoke(
        app,
        ["test", "smoke"],
        env={"API_URL": "http://from-env:1"},  # the CLI's own envvar binding, scoped to this invocation
        obj=make_cli_context(run_pytest=pytest_runner),
    )

    assert result.exit_code == 0, result.output
    assert pytest_runner.calls[0][1] == "http://from-env:1"


def test_smoke_treats_no_collected_tests_as_success() -> None:
    context = make_cli_context(run_pytest=FakePytestRunner(exit_code=int(pytest.ExitCode.NO_TESTS_COLLECTED)))

    assert runner.invoke(app, ["test", "smoke"], obj=context).exit_code == 0


@pytest.mark.parametrize(
    "code", [pytest.ExitCode.TESTS_FAILED, pytest.ExitCode.INTERNAL_ERROR, pytest.ExitCode.USAGE_ERROR]
)
def test_smoke_propagates_a_failing_pytest_exit_code(code: pytest.ExitCode) -> None:
    context = make_cli_context(run_pytest=FakePytestRunner(exit_code=int(code)))

    assert runner.invoke(app, ["test", "smoke"], obj=context).exit_code == int(code)


def test_smoke_explains_how_to_install_pytest_when_it_is_missing() -> None:
    missing = PytestNotInstalledError("pytest is not installed — run: uv sync --group dev")
    context = make_cli_context(run_pytest=FakePytestRunner(error=missing))

    result = runner.invoke(app, ["test", "smoke"], obj=context)

    assert result.exit_code == 1
    assert "uv sync --group dev" in result.output
