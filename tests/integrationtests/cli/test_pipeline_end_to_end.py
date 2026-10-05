"""The CLI over real wiring: the dataset arrives through a `file://` archive, the real devkit and loader read it, and
the model is a stub Ollama server on localhost. Nothing is faked or patched, so this is also what proves each command
is routed to the right collaborators; the command functions themselves hold no logic.
"""

import asyncio
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app
from backseat_driver.models import IngestTask, JobState
from backseat_driver.read.dataset.nuscenes_scene_loader import NuScenesSceneLoader
from backseat_driver.read.s3.s3_dataset_store import S3DatasetStore
from backseat_driver.read.s3.stored_scene_loader import StoredSceneLoader
from backseat_driver.read.s3.uploader import DatasetUploader
from backseat_driver.stacks import build_image_store, build_job_backend
from backseat_driver.transport.caption_worker import CaptionWorker
from backseat_driver.transport.ingest_worker import IngestWorker
from tests.ansi import plain
from tests.fakes import DiskS3Client, FakeCaptioner, FakeImageStore, FakeJobQueue, FakeJobStore, make_settings
from tests.nuscenes_dataset import (
    SCENE_LABELS,
    VERSION,
    build_nuscenes_archive,
    build_nuscenes_dataset,
    middle_image,
)
from tests.stub_server import Responder, StubServer, json_reply
from tests.waiting import wait_until

runner = CliRunner()
CAPTION = "a parked truck near construction"


@pytest.fixture
def ollama_url(stub_server: Callable[[Responder], StubServer]) -> str:
    return stub_server(lambda received: json_reply({"response": CAPTION})).url


@pytest.fixture
def cli_env(tmp_path: Path, ollama_url: str) -> dict[str, str]:
    """Points every external dependency of `describe` at something local: no network, no real cache."""
    return {
        "BACKSEAT_DRIVER_NUSCENES_URL": build_nuscenes_archive(tmp_path).as_uri(),
        "BACKSEAT_DRIVER_NUSCENES_DATAROOT": str(tmp_path / "cache"),
        "BACKSEAT_DRIVER_NUSCENES_VERSION": VERSION,
        "BACKSEAT_DRIVER_VLM_BACKEND": "ollama",
        "BACKSEAT_DRIVER_OLLAMA_URL": ollama_url,
        "BACKSEAT_DRIVER_OLLAMA_MODEL_NAME": "llava",
        "BACKSEAT_DRIVER_OUTPUT_DIR": str(tmp_path / "output"),
    }


def test_describe_fetches_the_dataset_and_describes_every_scene_with_its_reference_label(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    output = tmp_path / "result.json"

    result = runner.invoke(app, ["describe", "--camera", "front", "--output", str(output)], env=cli_env)

    assert result.exit_code == 0, result.output
    written = json.loads(output.read_text())
    assert [d["scene_name"] for d in written] == ["scene-0000", "scene-0001"]
    assert [d["reference_description"] for d in written] == SCENE_LABELS
    assert [d["description"] for d in written] == [CAPTION] * 2
    assert [d["image_path"] for d in written] == [middle_image(i) for i in range(2)]
    assert all((tmp_path / "cache" / d["image_path"]).is_file() for d in written)


def test_describe_honours_max_scenes(cli_env: dict[str, str], tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    result = runner.invoke(
        app, ["describe", "--camera", "front", "--max-scenes", "1", "--output", str(output)], env=cli_env
    )

    assert result.exit_code == 0, result.output
    assert len(json.loads(output.read_text())) == 1


@pytest.mark.parametrize("max_scenes", ["0", "-1"])
def test_describe_rejects_a_max_scenes_below_one_before_doing_any_work(
    cli_env: dict[str, str], tmp_path: Path, max_scenes: str
) -> None:
    output = tmp_path / "result.json"

    result = runner.invoke(
        app, ["describe", "--camera", "front", "--max-scenes", max_scenes, "--output", str(output)], env=cli_env
    )

    assert result.exit_code == 2
    assert "--max-scenes" in plain(result.output)
    assert not output.exists()
    assert not (tmp_path / "cache").exists()  # usage error comes before the dataset download


def test_describe_then_report_scores_the_descriptions_against_the_labels(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    # No --output: the file lands in <output dir>/<backend>__<model>.json, where `report` looks.
    described = runner.invoke(app, ["describe", "--camera", "front"], env=cli_env)
    assert described.exit_code == 0, described.output

    result = runner.invoke(app, ["report"], env=cli_env)
    html = (tmp_path / "output" / "report.html").read_text()

    assert result.exit_code == 0, result.output
    assert "scene-0000" in html
    assert "Parked truck, construction ahead" in html
    assert "data:image/jpeg;base64," in html  # images are inlined, so the page works without the dataset


def test_report_reads_the_images_from_the_dataroot_given_to_describe(cli_env: dict[str, str], tmp_path: Path) -> None:
    dataroot = str(tmp_path / "elsewhere")
    env = {k: v for k, v in cli_env.items() if k != "BACKSEAT_DRIVER_NUSCENES_DATAROOT"}
    described = runner.invoke(app, ["describe", "--camera", "front", "--dataroot", dataroot], env=env)
    assert described.exit_code == 0, described.output

    result = runner.invoke(app, ["report", "--dataroot", dataroot], env=env)
    html = (tmp_path / "output" / "report.html").read_text()

    assert result.exit_code == 0, result.output
    assert "data:image/jpeg;base64," in html


def test_describe_fails_clearly_when_the_dataset_cannot_be_fetched(cli_env: dict[str, str], tmp_path: Path) -> None:
    unreachable = {**cli_env, "BACKSEAT_DRIVER_NUSCENES_URL": (tmp_path / "gone.tgz").as_uri()}

    result = runner.invoke(
        app, ["describe", "--camera", "front", "--output", str(tmp_path / "x.json")], env=unreachable
    )

    assert result.exit_code != 0
    assert not (tmp_path / "x.json").exists()


def test_describe_requires_a_model(cli_env: dict[str, str], tmp_path: Path) -> None:
    without_model = {**cli_env, "BACKSEAT_DRIVER_OLLAMA_MODEL_NAME": ""}

    result = runner.invoke(
        app, ["describe", "--camera", "front", "--output", str(tmp_path / "x.json")], env=without_model
    )

    assert result.exit_code != 0
    assert "No model chosen for the ollama backend" in str(result.exception)
    assert not (tmp_path / "x.json").exists()


def test_describe_requires_a_camera_choice(cli_env: dict[str, str], tmp_path: Path) -> None:
    result = runner.invoke(app, ["describe", "--output", str(tmp_path / "x.json")], env=cli_env)

    assert result.exit_code == 2
    assert "--all-cameras" in plain(result.output)


def test_describe_rejects_all_cameras_together_with_camera(cli_env: dict[str, str], tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["describe", "--all-cameras", "--camera", "back", "--output", str(tmp_path / "x.json")], env=cli_env
    )

    assert result.exit_code == 2


def test_distributed_workers_over_the_real_loader_keep_the_reference_label(tmp_path: Path) -> None:
    dataroot = build_nuscenes_dataset(tmp_path / "nuscenes")
    queue, store, captioner, images = FakeJobQueue(), FakeJobStore(), FakeCaptioner("a truck"), FakeImageStore()
    loader = NuScenesSceneLoader(dataroot=str(dataroot), version=VERSION)
    job_id = uuid4()
    store.create_job(job_id, None, "txn-1")

    IngestWorker(loader, queue, store, images).handle(IngestTask(job_id=job_id, transaction_id="txn-1"))
    for task in queue.caption_tasks:
        CaptionWorker(captioner, store, images).handle(task)
    descriptions = store.list_descriptions(job_id)

    assert store.get_job(job_id).expected_scenes == len(SCENE_LABELS)
    assert [d.reference_description for d in descriptions] == SCENE_LABELS


class _ByteCountingCaptioner(FakeCaptioner):
    """Reads the image it is given, so it fails unless a real local file is there."""

    async def caption(self, image_path: str) -> str:
        return f"{len(await asyncio.to_thread(Path(image_path).read_bytes))} bytes"


def test_a_job_runs_from_the_bucket_alone_once_the_dataset_is_uploaded(tmp_path: Path) -> None:
    dataroot = build_nuscenes_dataset(tmp_path / "nuscenes")
    client = DiskS3Client(tmp_path / "buckets")
    dataset = S3DatasetStore("nuscenes", make_client=lambda _endpoint: client)
    asyncio.run(DatasetUploader(dataset).upload(str(dataroot), VERSION, ["CAM_FRONT"]))
    shutil.rmtree(dataroot)  # from here on no worker has the dataset on a disk
    queue, store = FakeJobQueue(), FakeJobStore()

    def make_loader(root: str) -> NuScenesSceneLoader:
        return NuScenesSceneLoader(dataroot=root, version=VERSION, camera_channels=["CAM_FRONT"])

    loader = StoredSceneLoader(dataset, VERSION, make_loader)
    job_id = uuid4()
    store.create_job(job_id, None, "txn-1")

    IngestWorker(loader, queue, store, dataset).handle(IngestTask(job_id=job_id, transaction_id="txn-1"))
    for task in queue.caption_tasks:
        CaptionWorker(_ByteCountingCaptioner(), store, dataset).handle(task)
    descriptions = store.list_descriptions(job_id)

    assert store.get_job(job_id).completed_scenes == len(SCENE_LABELS)
    assert [d.image_path for d in descriptions] == [middle_image(i) for i in range(len(SCENE_LABELS))]
    assert all(d.description.endswith(" bytes") for d in descriptions)
    assert [d.reference_description for d in descriptions] == SCENE_LABELS


async def test_the_monolith_reports_images_by_key_and_the_store_serves_them(tmp_path: Path) -> None:
    dataroot = build_nuscenes_dataset(tmp_path / "nuscenes")
    settings = make_settings(nuscenes_dataroot=str(dataroot), nuscenes_version=VERSION)
    images = build_image_store(settings)
    queue, store = build_job_backend(settings, _ByteCountingCaptioner(), images)
    job_id = uuid4()
    store.create_job(job_id, None, "txn-1")

    queue.enqueue_ingest(IngestTask(job_id=job_id, transaction_id="txn-1"))
    wait_until(lambda: store.get_job(job_id).state is JobState.COMPLETED, "the job to complete")
    descriptions = store.list_descriptions(job_id)

    assert [d.image_path for d in descriptions] == [middle_image(i) for i in range(len(SCENE_LABELS))]
    async with images.local_copy(images.uri_for(descriptions[0].image_path)) as path:
        assert path.read_bytes()


def test_describe_distributed_rejects_options_that_only_apply_to_the_monolith(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        ["describe", "--mode", "distributed", "--camera", "front", "--output", str(tmp_path / "x.json")],
        env=cli_env,
    )

    assert result.exit_code == 2
    assert "--camera" in plain(result.output)


def test_describe_distributed_requires_an_output_path(cli_env: dict[str, str]) -> None:
    result = runner.invoke(app, ["describe", "--mode", "distributed"], env=cli_env)

    assert result.exit_code == 2
    assert "--output" in plain(result.output)
