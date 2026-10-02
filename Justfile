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

# Build the static model-comparison HTML report from result JSON files
report *ARGS:
    uv run backseat-driver report {{ARGS}}

# Serve the model-comparison UI locally (default: every JSON in output/)
ui *ARGS:
    uv run backseat-driver ui {{ARGS}}

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

# Performance benchmarks (pytest-codspeed); run under `codspeed run` for CodSpeed measurements
bench:
    uv run pytest tests/benchmarks --codspeed

# Smoke tests against a running service (set API_URL to override target)
test-smoke:
    uv run backseat-driver test smoke --verbose

# System tests against a running API (`just dev`, or `just up`; API_URL overrides the target)
test-system:
    uv run pytest tests/systemtests -v

# All non-smoke tests
test-all:
    uv run pytest tests/unittests tests/integrationtests tests/systemtests -v --cov

# Same variables the app reads, so the host-run API listens where `test-smoke` and .env expect it.
set dotenv-load

api_host := env("BACKSEAT_DRIVER_API_HOST", "127.0.0.1")
api_port := env("BACKSEAT_DRIVER_API_PORT", "8080")

# Dev server with auto-reload; starts RabbitMQ + Postgres first so /ready passes (needs Docker)
dev: infra
    uv run fastapi dev backseat_driver/api/app.py --host {{api_host}} --port {{api_port}}

# Production-mode server on the host; binds all interfaces (needs `just infra`)
serve:
    uv run fastapi run backseat_driver/api/app.py --host 0.0.0.0 --port {{api_port}}

# RabbitMQ + Postgres in Docker (published on localhost) with the schema created, for host-run API/workers
infra:
    docker compose up -d --wait rabbitmq postgres
    uv run backseat-driver db init

# Stop the stack and the infra started by `just infra`
infra-down:
    docker compose down

# Host-run queue workers (distributed mode); need `just infra`
worker-ingest:
    uv run backseat-driver worker ingest

# ...and the caption worker (loads the model before consuming)
worker-caption:
    uv run backseat-driver worker caption

# The pipeline in the cli container (same as `just run`, but containerised): `just docker-run --max-scenes 2`
docker-run *ARGS:
    docker compose --profile cli run --build --rm cli run {{ARGS}}

# Distributed mode, all in Docker: API + RabbitMQ + Postgres + ingest/caption workers
up:
    docker compose up --build

# Same as `up`, with the API hot-reloading from ./backseat_driver
up-dev:
    docker compose -f docker-compose.yml -f docker/docker-compose.dev.yml up --build

# Stop the distributed stack
down:
    docker compose down

# Render the Kubernetes manifests without applying them
k8s-render:
    kubectl kustomize k8s

# Deploy to the current kubectl context (see docs/running.md first: dataset volume, secret)
k8s-apply:
    kubectl apply -k k8s

# Remove everything k8s-apply created (the PVCs go with it)
k8s-delete:
    kubectl delete -k k8s

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
