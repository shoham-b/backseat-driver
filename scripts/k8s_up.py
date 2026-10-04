"""Build the images, load them into a local kind cluster, install KEDA and deploy with autoscaling.

Usage: k8s_up.py <kind cluster> <keda version>
"""

import subprocess
import sys
from pathlib import Path

cluster, keda_version = sys.argv[1:]
kubectl = ["kubectl", "--context", f"kind-{cluster}"]
keda_manifest = f"https://github.com/kedacore/keda/releases/download/v{keda_version}/keda-{keda_version}.yaml"


def run(*command: str) -> None:
    subprocess.run(command, check=True)


Path("data").mkdir(exist_ok=True)

clusters = subprocess.run(["kind", "get", "clusters"], check=True, capture_output=True, text=True).stdout.split()
if cluster not in clusters:
    run("kind", "create", "cluster", "--config", "deploy/kind/cluster.yaml")

# --build-arg PYTHON_VERSION without a value takes it from the environment, which the Justfile exports.
for target in ["api", "ingest-worker", "caption-worker", "cli"]:
    image = f"backseat-driver-{target}:local"
    run(
        "docker",
        "build",
        "-f",
        "docker/Dockerfile",
        "--build-arg",
        "PYTHON_VERSION",
        "--target",
        target,
        "-t",
        image,
        ".",
    )
    run("kind", "load", "docker-image", "--name", cluster, image)

run(*kubectl, "apply", "--server-side", "-f", keda_manifest)
run(*kubectl, "wait", "-n", "keda", "--for=condition=Available", "deployment", "--all", "--timeout=180s")
run(*kubectl, "apply", "-k", "deploy/kind")
# A reloaded image keeps its tag, so running pods must be restarted to pick it up.
run(
    *kubectl,
    "-n",
    "backseat-driver",
    "rollout",
    "restart",
    "deploy/api",
    "deploy/ingest-worker",
    "deploy/caption-worker",
)
run(*kubectl, "-n", "backseat-driver", "rollout", "status", "deploy/api", "--timeout=300s")
