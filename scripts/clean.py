"""Remove build artifacts and caches."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ["dist", "site", ".pytest_cache", "htmlcov", "coverage.xml", "junit.xml"]

for name in ARTIFACTS:
    path = ROOT / name
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)

# The virtualenv's bytecode caches are rebuilt on import and not worth walking.
for path in ROOT.rglob("*"):
    if ".venv" in path.relative_to(ROOT).parts:
        continue
    if path.is_dir() and path.name == "__pycache__":
        shutil.rmtree(path)
    elif path.suffix == ".pyc":
        path.unlink(missing_ok=True)
