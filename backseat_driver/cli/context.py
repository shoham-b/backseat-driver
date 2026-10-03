"""Everything the CLI commands reach outside the process for, handed to them through the Typer context.

Commands read `ctx.obj` (a `CliContext`) instead of calling `get_settings()` or importing adapters themselves, so tests
pass a context of fakes with `runner.invoke(app, ..., obj=context)` and nothing has to be monkeypatched. Without
`obj`, `default_context()` wires the real thing. The heavy imports (transformers, nuscenes, celery, psycopg) stay inside
the factories below so `--help` and the lightweight commands don't pay for them.
"""

import functools
import http.server
import os
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass

import typer

from backseat_driver.captioning.captioner import Captioner
from backseat_driver.config import Settings, VlmBackend, get_settings
from backseat_driver.logger import LogFormat, setup_logging
from backseat_driver.scenes.dataset_cache import DatasetCache
from backseat_driver.scenes.scene_loader import SceneLoader


class PytestNotInstalledError(RuntimeError):
    pass


@dataclass(frozen=True)
class CliContext:
    settings: Settings
    configure_logging: Callable[[LogFormat, str], None]  # format, service name
    # run
    dataset_cache: DatasetCache
    build_loader: Callable[[str, str, str], SceneLoader]  # dataroot, version, camera_channel
    build_captioner: Callable[[Settings, VlmBackend | None, str | None], Captioner]  # settings, backend, model_name
    # db init
    init_schema: Callable[[str], None]  # database url
    # worker
    load_caption_model: Callable[[], None]
    start_worker: Callable[[list[str]], None]  # Celery worker argv
    # test smoke
    run_pytest: Callable[[list[str], str | None], int]  # pytest args, API_URL to export; returns the exit code
    # ui
    serve: Callable[[str, str, int, str | None], None]  # directory, host, port, URL to open once listening


def cli_context(ctx: typer.Context) -> CliContext:
    return ctx.obj if ctx.obj is not None else default_context()


def default_context() -> CliContext:
    return CliContext(
        settings=get_settings(),
        configure_logging=setup_logging,
        dataset_cache=_nuscenes_dataset_cache(get_settings()),
        build_loader=_build_nuscenes_loader,
        build_captioner=_build_captioner,
        init_schema=_init_schema,
        load_caption_model=_load_caption_model,
        start_worker=_start_worker,
        run_pytest=_run_pytest,
        serve=_serve,
    )


def _nuscenes_dataset_cache(settings: Settings) -> DatasetCache:
    from backseat_driver.scenes.nuscenes_dataset import NuScenesDatasetCache

    return NuScenesDatasetCache(settings.nuscenes_url)


def _build_nuscenes_loader(dataroot: str, version: str, camera_channel: str) -> SceneLoader:
    from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader

    return NuScenesSceneLoader(dataroot=dataroot, version=version, camera_channel=camera_channel)


def _build_captioner(settings: Settings, backend: VlmBackend | None, model_name: str | None) -> Captioner:
    from backseat_driver.captioning.factory import build_captioner

    return build_captioner(settings, backend=backend, model_name=model_name)


def _init_schema(database_url: str) -> None:
    from backseat_driver.jobs.postgres_job_store import PostgresJobStore

    PostgresJobStore(database_url).ensure_schema()


def _load_caption_model() -> None:
    from backseat_driver.tasks import caption_worker

    caption_worker()


def _start_worker(argv: list[str]) -> None:
    from backseat_driver.tasks import celery_app

    celery_app.worker_main(argv)


def _run_pytest(args: list[str], api_url: str | None) -> int:
    try:
        import pytest
    except ImportError:
        raise PytestNotInstalledError("pytest is not installed — run: uv sync --group dev") from None

    if api_url:
        os.environ["API_URL"] = api_url  # the smoke tests' `api_url` fixture reads it
    return int(pytest.main(args))


def _serve(directory: str, host: str, port: int, open_url: str | None) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    with http.server.ThreadingHTTPServer((host, port), handler) as server:
        if open_url:
            webbrowser.open(open_url)  # only once the port is bound, or the browser can beat the server
        server.serve_forever()
