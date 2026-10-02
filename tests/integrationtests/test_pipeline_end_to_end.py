"""The pipeline over a real (tiny) nuScenes dataset: real devkit, loader, writer and report; only the model is faked.

Unit tests monkeypatch the devkit, so this is what proves the pieces still fit together on actual dataset files.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from backseat_driver.captioning import factory
from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.config import get_settings
from backseat_driver.jobs.workers import CaptionWorker, IngestWorker
from backseat_driver.models import IngestTask
from backseat_driver.scenes.nuscenes_scene_loader import NuScenesSceneLoader
from tests.fakes import FakeCaptioner, FakeJobQueue, FakeJobStore
from tests.nuscenes_dataset import SCENE_LABELS, VERSION, build_nuscenes_dataset, middle_image

pytest.importorskip("nuscenes.nuscenes", reason="nuscenes-devkit (and its OpenCV libraries) is not installed")

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def dataroot(tmp_path: Path) -> Path:
    return build_nuscenes_dataset(tmp_path / "nuscenes")


@pytest.fixture
def captioner(monkeypatch: pytest.MonkeyPatch) -> FakeCaptioner:
    fake = FakeCaptioner("a parked truck near construction")
    monkeypatch.setattr(factory, "build_captioner", lambda *args, **kwargs: fake)
    return fake


def test_run_describes_every_scene_from_the_middle_frame_with_its_reference_label(
    dataroot: Path, captioner: FakeCaptioner, tmp_path: Path
) -> None:
    output = tmp_path / "result.json"

    result = runner.invoke(app, ["run", "--dataroot", str(dataroot), "--version", VERSION, "--output", str(output)])
    written = json.loads(output.read_text())

    assert result.exit_code == 0, result.output
    assert [d["scene_name"] for d in written] == ["scene-0000", "scene-0001"]
    assert [d["reference_description"] for d in written] == SCENE_LABELS
    assert [d["image_path"] for d in written] == [str(dataroot / middle_image(i)) for i in range(2)]
    assert all(Path(d["image_path"]).is_file() for d in written)
    assert captioner.seen_paths == [d["image_path"] for d in written]


def test_run_honours_max_scenes(dataroot: Path, captioner: FakeCaptioner, tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    result = runner.invoke(app, ["run", "--dataroot", str(dataroot), "--max-scenes", "1", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text())) == 1


def test_run_then_report_scores_the_descriptions_against_the_labels(
    dataroot: Path, captioner: FakeCaptioner, tmp_path: Path
) -> None:
    result_file = tmp_path / "result.json"
    html_file = tmp_path / "report.html"
    runner.invoke(app, ["run", "--dataroot", str(dataroot), "--output", str(result_file)])

    result = runner.invoke(app, ["report", str(result_file), "--output", str(html_file)])
    html = html_file.read_text()

    assert result.exit_code == 0, result.output
    assert "scene-0000" in html
    assert "Parked truck, construction ahead" in html
    assert "data:image/jpeg;base64," in html  # images are inlined, so the page works without the dataset


def test_run_fails_clearly_when_the_dataset_is_missing(captioner: FakeCaptioner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "--dataroot", str(tmp_path / "nowhere"), "--output", str(tmp_path / "x.json")])

    assert result.exit_code != 0
    assert not (tmp_path / "x.json").exists()


def test_distributed_workers_over_the_real_loader_keep_the_reference_label(dataroot: Path) -> None:
    queue, store, captioner = FakeJobQueue(), FakeJobStore(), FakeCaptioner("a truck")
    loader = NuScenesSceneLoader(dataroot=str(dataroot), version=VERSION)
    job_id = uuid4()
    store.create_job(job_id, None, "txn-1")

    IngestWorker(loader, queue, store).handle(IngestTask(job_id=job_id, transaction_id="txn-1"))
    for task in queue.caption_tasks:
        CaptionWorker(captioner, store).handle(task)
    descriptions = store.list_descriptions(job_id)

    assert store.get_job(job_id).expected_scenes == len(SCENE_LABELS)
    assert [d.reference_description for d in descriptions] == SCENE_LABELS
