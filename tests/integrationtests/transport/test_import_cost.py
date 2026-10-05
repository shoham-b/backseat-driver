"""The ingest worker starts a process per queued message, so what its entry point imports is paid on every job.

Each check runs in a fresh interpreter: `sys.modules` of the test process already holds whatever other tests imported.
"""

import subprocess
import sys

import pytest

HEAVY = ["torch", "transformers", "nuscenes", "matplotlib", "sklearn", "scipy"]


def _imported_after(statement: str) -> set[str]:
    probe = f"import sys; {statement}; print(' '.join(sorted(sys.modules)))"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    return set(result.stdout.split())


@pytest.mark.parametrize("heavy", HEAVY)
def test_the_ingest_entry_point_does_not_import(heavy: str) -> None:
    imported = _imported_after("from backseat_driver.tasks import celery_app")

    assert heavy not in imported


@pytest.mark.parametrize("heavy", HEAVY)
def test_finding_keyframes_does_not_import(heavy: str) -> None:
    imported = _imported_after("from backseat_driver.read.dataset.nuscenes_scene_loader import NuScenesSceneLoader")

    assert heavy not in imported
