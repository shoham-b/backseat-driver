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

# Selenium tests of the model-comparison UI (headless Chrome; CHROME_BIN / CHROMEDRIVER override the browser)
test-ui:
    uv run pytest tests/uitests -v

# System tests against a running API (`just infra` + `just dev`, or `just up`; API_URL overrides the target)
test-system:
    uv run pytest tests/systemtests -v

# All non-smoke tests
test-all:
    uv run pytest tests/unittests tests/integrationtests tests/systemtests -v --cov

# Same variables the app reads, so the host-run API listens where `test-smoke` and .env expect it.
set dotenv-load

api_host := env("BACKSEAT_DRIVER_API_HOST", "127.0.0.1")
api_port := env("BACKSEAT_DRIVER_API_PORT", "8080")

# Local dev server with auto-reload; no Docker. Monolith mode: /describe and /jobs all work in this one process, with no broker, database or workers (job state is lost on restart)
dev:
    uv run fastapi dev backseat_driver/api/app.py --host {{api_host}} --port {{api_port}}

# Same server as `dev`, but in distributed mode: /jobs goes through RabbitMQ + Postgres (`just infra`) to host workers (`just worker-ingest`, `just worker-caption`)
dev-distributed: infra
    BACKSEAT_DRIVER_MODE=distributed uv run fastapi dev backseat_driver/api/app.py --host {{api_host}} --port {{api_port}}

# Production-mode server, all interfaces. Monolith unless BACKSEAT_DRIVER_MODE=distributed (Kubernetes sets it; locally `just infra` first)
serve:
    uv run fastapi run backseat_driver/api/app.py --host 0.0.0.0 --port {{api_port}}

# LOCAL ONLY: RabbitMQ + Postgres in Docker on localhost, schema created (production gets these from Kubernetes)
infra:
    docker compose up -d --wait rabbitmq postgres
    uv run backseat-driver db init

# Stop the stack and the infra started by `just infra`
infra-down:
    docker compose down

# Host-run queue workers for local work (production runs them in Kubernetes); start the local infra first (needs Docker)
worker-ingest: infra
    uv run backseat-driver worker ingest

# ...and the caption worker (loads the model before consuming)
worker-caption: infra
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

# Render the Kubernetes manifests (needs kubectl)
k8s-render:
    kubectl kustomize deploy/k8s

# Validate the rendered manifests against the Kubernetes schemas (no cluster needed)
k8s-validate:
    kubectl kustomize deploy/k8s > /tmp/backseat-driver-k8s.yaml
    uvx kubernetes-validate /tmp/backseat-driver-k8s.yaml

# Deploy to the current kubectl context (see docs/deployment.md first: dataset volume, credentials)
k8s-apply:
    kubectl apply -k deploy/k8s

keda_version := "2.18.1"
kind_cluster := "backseat-driver"
# Pinned to the kind context so a stale current-context can never point these at another cluster.
kubectl := "kubectl --context kind-" + kind_cluster

# Local Kubernetes (kind): builds the images, loads them, installs KEDA and deploys with queue-depth autoscaling. API on :8080
k8s-up:
    mkdir -p data
    kind get clusters | grep -qx {{kind_cluster}} || kind create cluster --config deploy/kind/cluster.yaml
    for target in api ingest-worker caption-worker cli; do \
        docker build -f docker/Dockerfile --target $target -t backseat-driver-$target:local . || exit 1; \
        kind load docker-image --name {{kind_cluster}} backseat-driver-$target:local || exit 1; \
    done
    {{kubectl}} apply --server-side -f https://github.com/kedacore/keda/releases/download/v{{keda_version}}/keda-{{keda_version}}.yaml
    {{kubectl}} wait -n keda --for=condition=Available deployment --all --timeout=180s
    {{kubectl}} apply -k deploy/kind
    # A reloaded image keeps its tag, so running pods must be restarted to pick it up.
    {{kubectl}} -n backseat-driver rollout restart deploy/api deploy/ingest-worker deploy/caption-worker
    {{kubectl}} -n backseat-driver rollout status deploy/api --timeout=300s

# Watch the autoscaler and worker replicas on the kind cluster
k8s-status:
    {{kubectl}} -n backseat-driver get scaledobject,hpa,deploy,pods

# Delete the local kind cluster and everything in it
k8s-down:
    kind delete cluster --name {{kind_cluster}}

# Remove everything k8s-apply created (the PVCs go with it)
k8s-delete:
    kubectl delete -k deploy/k8s

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
