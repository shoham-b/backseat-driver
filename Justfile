# Backseat Driver — dev task runner
# Install just: https://github.com/casey/just

set windows-shell := ["bash", "-c"]

default:
    @just --list

# Sync all dev dependencies
sync:
    uv sync --group dev

# Run the scene-description pipeline over the local nuScenes dataset
run *ARGS:
    uv run backseat-driver run {{ARGS}}

# Auto-fix and format
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# Lint without fixing (CI mode)
lint:
    uv run ruff check .
    uv run ruff format --check .

# Type check
typecheck:
    uv run ty check backseat_driver tests

# Unit + integration tests with coverage
test:
    uv run pytest tests/unittests tests/integrationtests --cov --cov-report=term-missing

# System tests via Docker Compose — builds images, runs system + smoke tests against containerised API
test-compose:
    docker compose --profile test run --build --rm systemtest
    docker compose --profile test down

# Benchmarks (CodSpeed; locally this just runs them, CI does the measuring)
bench:
    uv run --with pytest-codspeed pytest tests/benchmarks --codspeed

# Smoke tests against a running service (set API_URL to override target)
test-smoke:
    uv run backseat-driver test smoke --verbose

# Full system tests — auto-starts service locally
test-system:
    uv run pytest tests/systemtests -v

# All non-smoke tests
test-all:
    uv run pytest tests/unittests tests/integrationtests tests/systemtests -v --cov

# Dev server with auto-reload
dev:
    uv run fastapi dev backseat_driver/api/app.py

# Production-mode server
serve:
    uv run fastapi run backseat_driver/api/app.py --host 0.0.0.0 --port 8080

# Distributed mode: API + RabbitMQ + Postgres + ingest/caption workers
up:
    docker compose up --build

# Stop the distributed stack
down:
    docker compose down



# Build HTML docs
docs:
    uv run --group docs mkdocs build

# Serve docs with live reload
docs-open:
    uv run --group docs mkdocs serve

# Install pre-commit hooks
hooks:
    uv run pre-commit install

# Run pre-commit on all files
check:
    uv run pre-commit run --all-files





# Remove build artifacts and cache
clean:
    rm -rf dist/ site/ .pytest_cache/ htmlcov/ coverage.xml junit.xml
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
