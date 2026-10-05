"""The read-process-write core must be complete on its own: it never imports the layers added to scale it out.

`transport/` (the queue, its workers and the job store), `read/s3/` (the bucket) and `write/job_store/` (the database
tables and queries) exist only because the process step runs as tasks and can run on another machine. The core, and
the platform SDKs those layers wrap, stay out.
"""

import ast
from pathlib import Path

import pytest

import backseat_driver

ROOT = Path(backseat_driver.__file__).parent
CORE = ["models", "read", "process", "write", "pipeline.py"]
ADDED_LAYERS = ("backseat_driver.transport", "backseat_driver.read.s3", "backseat_driver.write.job_store")
LAYER_SDKS = ("celery", "kombu", "boto3", "sqlalchemy", "psycopg")


def _core_files() -> list[Path]:
    files: list[Path] = []
    for name in CORE:
        path = ROOT / name
        files += [path] if path.suffix == ".py" else path.rglob("*.py")
    layers = [ROOT / "read" / "s3", ROOT / "write" / "job_store"]
    return [f for f in files if not any(layer in f.parents for layer in layers)]


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_the_core_does_not_import_an_added_layer(path: Path) -> None:
    imported = _imports(path)

    offending = {name for name in imported if name.startswith(ADDED_LAYERS) or name.split(".")[0] in LAYER_SDKS}

    assert not offending
