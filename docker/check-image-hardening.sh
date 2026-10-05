#!/usr/bin/env bash
# Checks the images the `kind` CI job builds: every service runs as the unprivileged uid, and the API still starts
# with a read-only root filesystem and no capabilities (the way a hardened pod runs it).
set -euo pipefail

for service in api ingest-worker caption-worker; do
  uid="$(docker run --rm --entrypoint id "backseat-driver-${service}:local" -u)"
  if [[ "$uid" != "10001" ]]; then
    echo "::error::backseat-driver-${service} runs as uid ${uid}, expected 10001"
    exit 1
  fi
  echo "ok: ${service} runs as uid ${uid}"
done

# Monolith mode keeps its jobs in SQLite, so the file moves to the tmpfs. The Ollama backend is never contacted at startup.
container="$(docker run -d --read-only --tmpfs /tmp --cap-drop ALL -p 18080:8080 \
  -e BACKSEAT_DRIVER_VLM_BACKEND=ollama \
  -e BACKSEAT_DRIVER_OLLAMA_MODEL_NAME=unused \
  -e BACKSEAT_DRIVER_JOBS_DB_PATH=/tmp/jobs.db \
  backseat-driver-api:local)"
trap 'docker rm -f "$container" >/dev/null' EXIT

deadline=$((SECONDS + 60))
until curl -fsS http://localhost:18080/health >/dev/null; do
  if ((SECONDS >= deadline)); then
    echo "::error::the API did not come up read-only"
    docker logs "$container"
    exit 1
  fi
  sleep 2
done
echo "ok: the API serves /health with --read-only --cap-drop ALL"
