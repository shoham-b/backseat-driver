# Backseat Driver — dev task runner
# Install just: https://github.com/casey/just

# PowerShell on Windows, `sh` elsewhere. Recipes marked [unix] (system tests, distributed dev, kind) are POSIX-only.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# The compose file lives in docker/, but paths and .env resolve from the repo root.
compose := "docker compose -f docker/docker-compose.yml --project-directory ."

# Run any docker compose command against the stack, e.g. `just compose --profile ui up ui`
compose *ARGS:
    {{compose}} {{ARGS}}

default:
    @just --list

# Run the scene-description pipeline over the local nuScenes dataset
describe *ARGS:
    uv run backseat-driver describe {{ARGS}}

# Build the static model-comparison HTML report from result JSON files
report *ARGS:
    uv run backseat-driver report {{ARGS}}

# Serve the model-comparison UI: every JSON in output/, plus the API's jobs with BACKSEAT_DRIVER_UI_ALL_JOBS=true
ui:
    uv run fastapi run backseat_driver/show/ui_server.py --host {{ui_host}} --port {{ui_port}}

# Auto-fix and format
fmt:
    uv run ruff check --fix .
    uv run ruff format .

# Lint without fixing (CI mode)
lint:
    uv run ruff check .
    uv run ruff format --check .

typecheck:
    uv run ty check backseat_driver tests

# Unit + integration tests with coverage
test:
    uv run pytest tests/unittests tests/integrationtests --cov --cov-report=term-missing

# System tests: builds the Docker Compose stack and runs system + smoke tests against it
[unix]
test-system:
    #!/usr/bin/env bash
    set -euo pipefail
    trap '{{compose}} --profile test down' EXIT
    {{compose}} --profile test run --build --rm systemtest

# System tests against an already running API (`just dev`, `just up`, a staging URL), no Docker: `just test-system-url http://localhost:8080`
test-system-url url:
    uv run pytest tests/systemtests -v --api-url {{url}}

# Performance benchmarks (pytest-codspeed); run under `codspeed run` for CodSpeed measurements
bench:
    uv run pytest tests/benchmarks --codspeed

# Smoke tests against a running service (set API_URL to override target)
test-smoke:
    uv run backseat-driver test smoke --verbose

# Selenium tests of the model-comparison UI (headless Chrome; CHROME_BIN / CHROMEDRIVER override the browser)
test-ui:
    uv run pytest tests/uitests -v

# Unit + integration tests, then the containerised system tests
[unix]
test-all: test test-system

# Same variables the app reads, so the host-run API listens where `test-smoke` and .env expect it.
set dotenv-load

# Single source of truth for the Python version; compose and docker builds pick it up from the environment.
export PYTHON_VERSION := trim(read(justfile_directory() / ".python-version"))

api_host := env("BACKSEAT_DRIVER_API_HOST", "127.0.0.1")
api_port := env("BACKSEAT_DRIVER_API_PORT", "8080")
ui_host := env("BACKSEAT_DRIVER_UI_HOST", "127.0.0.1")
ui_port := env("BACKSEAT_DRIVER_UI_PORT", "8081")

# Local dev server with auto-reload; no Docker. Monolith mode: /describe and /jobs all work in this one process, with no broker, database or workers (job state is lost on restart)
dev:
    uv run fastapi dev backseat_driver/api/app.py --host {{api_host}} --port {{api_port}}

# Same server as `dev`, but in distributed mode: /jobs goes through RabbitMQ + Postgres (`just infra`) to host workers (`just worker-ingest`, `just worker-caption`)
[unix]
dev-distributed: infra
    BACKSEAT_DRIVER_MODE=distributed uv run fastapi dev backseat_driver/api/app.py --host {{api_host}} --port {{api_port}}

# Production-mode server, all interfaces. Monolith unless BACKSEAT_DRIVER_MODE=distributed (Kubernetes sets it; locally `just infra` first)
serve:
    uv run fastapi run backseat_driver/api/app.py --host 0.0.0.0 --port {{api_port}}

# LOCAL ONLY: RabbitMQ + Postgres + a dev S3 store in Docker on localhost, schema created (production gets these from Kubernetes)
infra:
    {{compose}} up -d --wait rabbitmq postgres s3
    uv run backseat-driver db init

# Stop the stack and the infra started by `just infra`
infra-down:
    {{compose}} down

# Copy the local dataset into the dev S3 bucket (once; the host workers read it from there). Needs the BACKSEAT_DRIVER_DATASET_BUCKET block of .env.example
dataset-upload: infra
    uv run backseat-driver dataset upload

# Host-run queue workers for local work (production runs them in Kubernetes); start the local infra first (needs Docker)
worker-ingest: infra
    uv run backseat-driver worker ingest

# ...and the caption worker (loads the model before consuming)
worker-caption: infra
    uv run backseat-driver worker caption

# The pipeline in the cli container (same as `just describe`, but containerised): `just docker-run --max-scenes 2`
docker-run *ARGS:
    {{compose}} --profile cli run --build --rm cli describe {{ARGS}}

# Distributed mode, all in Docker: API + RabbitMQ + Postgres + ingest/caption workers
up:
    {{compose}} up --build

# Same as `up`, with the API hot-reloading from ./backseat_driver
up-dev:
    {{compose}} -f docker/docker-compose.dev.yml up --build

down:
    {{compose}} down

# Render the Kubernetes manifests (needs kubectl)
k8s-render:
    kubectl kustomize deploy/k8s

# Validate the rendered manifests against the Kubernetes schemas (no cluster needed)
[unix]
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
[unix]
k8s-up:
    mkdir -p data
    kind get clusters | grep -qx {{kind_cluster}} || kind create cluster --config deploy/kind/cluster.yaml
    for target in api ingest-worker caption-worker cli; do \
        docker build -f docker/Dockerfile --build-arg PYTHON_VERSION --target $target -t backseat-driver-$target:local . || exit 1; \
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

docs:
    uv run --group docs mkdocs build -f docs/mkdocs.yml

# Serve docs with live reload
docs-open:
    uv run --group docs mkdocs serve -f docs/mkdocs.yml

hooks:
    uv run pre-commit install

check:
    uv run pre-commit run --all-files

clean:
    uvx pyclean --debris cache coverage pytest --erase dist site junit.xml --yes .
