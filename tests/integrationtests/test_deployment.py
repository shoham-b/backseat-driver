"""Keeps the Kubernetes manifests, Dockerfile and compose file consistent with the code they deploy.

None of these need a cluster or a Docker daemon: a manifest that points at a missing setting, CLI command or
route would otherwise only fail once it is applied.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import typer.main
import yaml

from backseat_driver.api.app import app as api_app
from backseat_driver.cli import __main__ as _main  # noqa: F401 - registers every subcommand
from backseat_driver.cli import app as cli_app
from backseat_driver.config import RunMode, Settings
from backseat_driver.transport.celery_job_queue import CAPTION_QUEUE, INGEST_QUEUE

ROOT = Path(__file__).parents[2]
K8S = ROOT / "deploy" / "k8s"
KEDA = ROOT / "deploy" / "components" / "keda-autoscaling"
ENV_PREFIX = "BACKSEAT_DRIVER_"


def _documents(path: Path) -> list[dict[str, Any]]:
    return [doc for doc in yaml.safe_load_all(path.read_text()) if doc]


def _all_manifests() -> list[dict[str, Any]]:
    kustomization = yaml.safe_load((K8S / "kustomization.yaml").read_text())
    return [doc for name in kustomization["resources"] for doc in _documents(K8S / name)]


def _of_kind(kind: str) -> list[dict[str, Any]]:
    return [doc for doc in _all_manifests() if doc["kind"] == kind]


def _pod_specs() -> Iterator[tuple[str, dict[str, Any]]]:
    for doc in [*_of_kind("Deployment"), *_of_kind("StatefulSet"), *_of_kind("Job")]:
        yield doc["metadata"]["name"], doc["spec"]["template"]["spec"]


def _our_containers() -> Iterator[tuple[str, dict[str, Any]]]:
    for name, pod in _pod_specs():
        for container in pod["containers"]:
            if container["image"].startswith("ghcr.io/shoham-b/backseat-driver-"):
                yield name, container


def _parse_without_running(args: list[str]) -> None:
    """Resolve the (sub)command and parse its options exactly as the entrypoint would, raising on any mismatch.

    Duck-typed on purpose: typer vendors its own copy of click, so `isinstance` against `click` would never match.
    """
    command: Any = typer.main.get_command(cli_app)
    name, context, resolved = "backseat-driver", None, 0
    while hasattr(command, "resolve_command"):
        context = command.make_context(name, [], parent=context, resilient_parsing=True)  # groups only route
        name, command, args = command.resolve_command(context, args)
        assert command is not None, f"unknown command {name!r}"
        resolved += 1
    assert resolved, args  # a bare group would just print its help
    command.make_context(name, args, parent=context)  # the leaf's options are parsed strictly


def test_every_manifest_file_is_listed_in_the_kustomization() -> None:
    listed = set(yaml.safe_load((K8S / "kustomization.yaml").read_text())["resources"])

    on_disk = {path.name for path in K8S.glob("*.yaml")} - {"kustomization.yaml"}

    assert listed == on_disk


def test_every_object_lives_in_the_declared_namespace_or_is_the_namespace() -> None:
    kustomization = yaml.safe_load((K8S / "kustomization.yaml").read_text())

    namespaces = [doc["metadata"]["name"] for doc in _of_kind("Namespace")]

    assert namespaces == [kustomization["namespace"]]


def test_configuration_keys_are_real_settings() -> None:
    fields = set(Settings.model_fields)
    keys = [
        key
        for doc in [*_of_kind("ConfigMap"), *_of_kind("Secret")]
        for key in (doc.get("data") or doc.get("stringData") or {})
        if key.startswith(ENV_PREFIX)
    ]

    unknown = [key for key in keys if key.removeprefix(ENV_PREFIX).lower() not in fields]

    assert keys
    assert not unknown


def test_container_args_are_valid_cli_invocations() -> None:
    containers = [c for _, c in _our_containers() if c.get("args")]

    for container in containers:
        _parse_without_running([str(arg) for arg in container["args"]])

    assert {c["args"][0] for c in containers} == {"dataset", "db", "worker"}


def test_our_images_are_the_ones_the_docker_workflow_publishes() -> None:
    workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text()
    published = set(re.findall(r"tags: (ghcr\.io/\S+?):latest", workflow))

    used = {container["image"] for _, container in _our_containers()}

    assert used <= published


def test_our_pods_run_as_non_root_without_privilege_escalation() -> None:
    pods = dict(_pod_specs())

    for name, container in _our_containers():
        assert pods[name]["securityContext"]["runAsNonRoot"] is True, name
        assert container["securityContext"]["allowPrivilegeEscalation"] is False, name
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"], name


def test_api_probes_hit_real_routes() -> None:
    routes = set(api_app.openapi()["paths"])
    (api,) = [c for _, c in _our_containers() if c["name"] == "api"]

    probed = {api[probe]["httpGet"]["path"] for probe in ("livenessProbe", "readinessProbe", "startupProbe")}

    assert probed <= routes
    assert api["readinessProbe"]["httpGet"]["path"] == "/ready"  # dependencies, not just the process


def test_every_service_selects_a_workload() -> None:
    labels = [doc["spec"]["template"]["metadata"]["labels"] for doc in _of_kind("Deployment") + _of_kind("StatefulSet")]

    for service in _of_kind("Service"):
        assert any(service["spec"]["selector"].items() <= pod_labels.items() for pod_labels in labels), service


def test_every_referenced_volume_claim_is_defined() -> None:
    claims = {doc["metadata"]["name"] for doc in _of_kind("PersistentVolumeClaim")}

    referenced = {
        volume["persistentVolumeClaim"]["claimName"]
        for _, pod in _pod_specs()
        for volume in pod.get("volumes", [])
        if "persistentVolumeClaim" in volume
    }

    assert referenced <= claims


def test_dataset_volume_is_mounted_read_only_everywhere() -> None:
    for name, pod in _pod_specs():
        for volume in pod.get("volumes", []):
            if volume.get("persistentVolumeClaim", {}).get("claimName") == "nuscenes-data":
                assert volume["persistentVolumeClaim"]["readOnly"] is True, name


@pytest.mark.parametrize("stage", ["cli", "api", "ingest-worker", "caption-worker"])
def test_runtime_images_drop_root(stage: str) -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text()

    runtime = dockerfile.split(f"AS {stage}\n", 1)[1].split("\n# ──", 1)[0]

    assert re.search(r"^USER 10001$", runtime, re.MULTILINE)


def test_dockerfile_does_not_float_on_the_latest_uv() -> None:
    for image in (ROOT / "docker").glob("Dockerfile*"):
        assert "astral-sh/uv:latest" not in image.read_text(), image.name


def test_compose_ui_service_serves_on_all_interfaces() -> None:
    compose = yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())

    ui = compose["services"]["ui"]

    assert ui["entrypoint"][:2] == ["fastapi", "run"]
    assert ui["entrypoint"][ui["entrypoint"].index("--host") + 1] == "0.0.0.0"
    assert ui["profiles"] == ["ui"]


def test_compose_cli_user_is_overridable_so_bind_mounted_output_is_writable() -> None:
    compose = yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())

    assert "LOCAL_UID" in compose["services"]["cli"]["user"]


def test_example_run_job_is_a_valid_invocation_on_the_defined_volumes() -> None:
    (job,) = _documents(K8S / "examples" / "run-job.yaml")
    pod = job["spec"]["template"]["spec"]
    (container,) = pod["containers"]
    claims = {doc["metadata"]["name"] for doc in _of_kind("PersistentVolumeClaim")}

    _parse_without_running([str(arg) for arg in container["args"]])

    assert job["metadata"]["namespace"] == yaml.safe_load((K8S / "kustomization.yaml").read_text())["namespace"]
    assert {v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v} <= claims
    assert {v["name"] for v in pod["volumes"] if "emptyDir" in v} == {"output"}  # world-writable, so no fsGroup needed


def test_cluster_runs_in_distributed_mode_not_the_monolith_default() -> None:
    (config,) = [doc for doc in _of_kind("ConfigMap") if doc["metadata"]["name"] == "backseat-driver-config"]

    assert config["data"]["BACKSEAT_DRIVER_MODE"] == RunMode.DISTRIBUTED


def test_each_worker_runs_its_own_image() -> None:
    images = {name: container["image"] for name, container in _our_containers() if name.endswith("-worker")}

    assert images == {
        "ingest-worker": "ghcr.io/shoham-b/backseat-driver-ingest-worker",
        "caption-worker": "ghcr.io/shoham-b/backseat-driver-caption-worker",
    }


def test_autoscalers_target_the_workers_and_watch_the_queues_they_consume() -> None:
    scaled = {
        doc["metadata"]["name"]: doc for doc in _documents(KEDA / "autoscaling.yaml") if doc["kind"] == "ScaledObject"
    }
    deployments = {doc["metadata"]["name"] for doc in _of_kind("Deployment")}

    queues = {name: obj["spec"]["triggers"][0]["metadata"]["queueName"] for name, obj in scaled.items()}

    assert queues == {"caption-worker": CAPTION_QUEUE}
    assert {obj["spec"]["scaleTargetRef"]["name"] for obj in scaled.values()} <= deployments
    assert all(obj["spec"]["minReplicaCount"] >= 1 for obj in scaled.values())  # the model must stay loaded


def _ingest_scaled_job() -> dict[str, Any]:
    (job,) = [doc for doc in _documents(KEDA / "autoscaling.yaml") if doc["kind"] == "ScaledJob"]
    return job


def test_ingest_runs_as_a_job_per_queued_task_with_keda() -> None:
    job = _ingest_scaled_job()
    (container,) = job["spec"]["jobTargetRef"]["template"]["spec"]["containers"]
    patched = yaml.safe_load((KEDA / "kustomization.yaml").read_text())["patches"]

    _parse_without_running([str(arg) for arg in container["args"]])

    assert job["spec"]["triggers"][0]["metadata"]["queueName"] == INGEST_QUEUE
    assert container["args"] == ["worker", "ingest", "--once"]  # a Job must exit after its task
    assert container["image"] == "ghcr.io/shoham-b/backseat-driver-ingest-worker"
    assert any("$patch: delete" in p["patch"] and p["target"]["name"] == "ingest-worker" for p in patched)


def _compose_services() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())["services"]


def test_no_worker_mounts_the_dataset_in_the_cluster() -> None:
    pods = dict(_pod_specs())

    mounting = {
        name
        for name, pod in pods.items()
        if any(
            volume.get("persistentVolumeClaim", {}).get("claimName") == "nuscenes-data"
            for volume in pod.get("volumes", [])
        )
    }

    assert "dataset-upload" in mounting
    assert not {name for name in mounting if name.endswith("-worker")}
    assert not any(
        volume.get("persistentVolumeClaim", {}).get("claimName") == "nuscenes-data"
        for volume in _ingest_scaled_job()["spec"]["jobTargetRef"]["template"]["spec"].get("volumes", [])
    )


def test_only_the_upload_service_mounts_the_dataset_in_compose() -> None:
    services = _compose_services()

    mounts_data = {
        name
        for name in ("dataset-upload", "ingest-worker", "caption-worker")
        if any("./data" in v for v in services[name].get("volumes", []))
    }

    assert mounts_data == {"dataset-upload"}


def test_the_cluster_bucket_is_the_one_the_dev_store_creates() -> None:
    (config,) = [doc for doc in _of_kind("ConfigMap") if doc["metadata"]["name"] == "backseat-driver-config"]
    (store,) = [doc for doc in _of_kind("Deployment") if doc["metadata"]["name"] == "s3"]
    (container,) = store["spec"]["template"]["spec"]["containers"]
    created = {entry["value"] for entry in container["env"] if entry["name"].endswith("INITIAL_BUCKETS")}

    assert {config["data"]["BACKSEAT_DRIVER_DATASET_BUCKET"]} == created


def test_compose_ingest_waits_for_the_upload_and_every_worker_gets_the_bucket() -> None:
    services = _compose_services()

    for name in ("ingest-worker", "caption-worker"):
        assert services[name]["environment"]["BACKSEAT_DRIVER_DATASET_BUCKET"], name
        assert services[name]["depends_on"]["s3"]["condition"] == "service_healthy", name
    assert services["ingest-worker"]["depends_on"]["dataset-upload"]["condition"] == "service_completed_successfully"


def test_the_report_ui_mounts_no_volume_and_probes_without_the_api() -> None:
    pods = dict(_pod_specs())
    (ui,) = [c for name, c in _our_containers() if name == "ui"]

    assert "volumes" not in pods["ui"]
    assert "volumeMounts" not in ui
    assert {"name": "BACKSEAT_DRIVER_UI_ALL_JOBS", "value": "true"} in ui["env"]
    assert ui["readinessProbe"]["httpGet"]["path"] == "/healthz"


def test_every_compose_service_in_distributed_mode_is_given_the_dataset_bucket() -> None:
    services = _compose_services()

    distributed = {
        name
        for name, service in services.items()
        if service.get("environment", {}).get("BACKSEAT_DRIVER_MODE") == RunMode.DISTRIBUTED
    }

    assert {"api", "ingest-worker", "caption-worker", "db-init"} <= distributed
    for name in distributed:
        assert services[name]["environment"].get("BACKSEAT_DRIVER_DATASET_BUCKET"), (
            name
        )  # Settings refuses to load without it


PRODUCTION = ROOT / "deploy" / "production"


def _production_kustomization() -> dict[str, Any]:
    return yaml.safe_load((PRODUCTION / "kustomization.yaml").read_text())


def test_production_pins_every_image_to_a_release_not_latest() -> None:
    pinned = {image["name"]: image["newTag"] for image in _production_kustomization()["images"]}

    used = {container["image"] for _, container in _our_containers()}

    assert set(pinned) == used
    assert all(re.fullmatch(r"v\d+\.\d+\.\d+", tag) for tag in pinned.values())


def test_production_config_patches_only_touch_real_settings() -> None:
    patches = [
        op
        for patch in _production_kustomization()["patches"]
        if patch.get("target", {}).get("kind") == "ConfigMap"
        for op in yaml.safe_load(patch["patch"])
    ]

    keys = [op["path"].removeprefix("/data/") for op in patches]

    assert keys
    for key in keys:
        assert key.startswith("AWS_") or key.removeprefix(ENV_PREFIX).lower() in Settings.model_fields
