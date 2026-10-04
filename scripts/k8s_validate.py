"""Validate the rendered Kubernetes manifests against the Kubernetes schemas (no cluster needed)."""

import subprocess
import tempfile
from pathlib import Path

rendered = subprocess.run(["kubectl", "kustomize", "deploy/k8s"], check=True, capture_output=True, text=True).stdout

with tempfile.TemporaryDirectory() as tmp:
    manifest = Path(tmp) / "backseat-driver-k8s.yaml"
    manifest.write_text(rendered)
    subprocess.run(["uvx", "kubernetes-validate", str(manifest)], check=True)
