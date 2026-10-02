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
from backseat_driver.config import Settings

ROOT = Path(__file__).parents[2]
K8S = ROOT / "deploy" / "k8s"
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

    assert {c["args"][0] for c in containers} == {"db", "worker", "ui"}


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


@pytest.mark.parametrize("stage", ["cli", "api"])
def test_runtime_images_drop_root(stage: str) -> None:
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text()

    runtime = dockerfile.split(f"AS {stage}\n", 1)[1].split("\n# ──", 1)[0]

    assert re.search(r"^USER 10001$", runtime, re.MULTILINE)


def test_dockerfile_does_not_float_on_the_latest_uv() -> None:
    for image in (ROOT / "docker").glob("Dockerfile*"):
        assert "astral-sh/uv:latest" not in image.read_text(), image.name


def test_compose_ui_service_serves_on_all_interfaces() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    ui = compose["services"]["ui"]

    assert ui["command"][0] == "ui"
    assert "0.0.0.0" in ui["command"]
    assert "--no-open" in ui["command"]
    assert ui["profiles"] == ["ui"]


def test_compose_cli_user_is_overridable_so_bind_mounted_output_is_writable() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert "LOCAL_UID" in compose["services"]["cli"]["user"]


def test_example_run_job_is_a_valid_invocation_on_the_defined_volumes() -> None:
    (job,) = _documents(K8S / "examples" / "run-job.yaml")
    pod = job["spec"]["template"]["spec"]
    (container,) = pod["containers"]
    claims = {doc["metadata"]["name"] for doc in _of_kind("PersistentVolumeClaim")}

    _parse_without_running([str(arg) for arg in container["args"]])

    assert job["metadata"]["namespace"] == yaml.safe_load((K8S / "kustomization.yaml").read_text())["namespace"]
    assert {v["persistentVolumeClaim"]["claimName"] for v in pod["volumes"] if "persistentVolumeClaim" in v} <= claims
    assert pod["securityContext"]["fsGroup"] == 10001  # so the non-root user can write to the results volume
