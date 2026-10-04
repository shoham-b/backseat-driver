#!/usr/bin/env bash
# Autoscaling check for the kind CI cluster (the `kind` job in .github/workflows/ci.yml): load the caption queue,
# then expect KEDA to scale the caption workers up, every caption to be recorded, and the workers to scale back down.
#
# Captions are injected straight onto the queue from a caption worker pod (using the project's own CeleryJobQueue and
# dataset store) because the CI cluster has no nuScenes dataset for the ingest worker to fan out. One placeholder image
# is put in the dataset bucket for them to point at.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"
CONTEXT="${KUBE_CONTEXT:-kind-backseat-driver}"
SCENES="${SCENES:-60}"
kubectl() { command kubectl --context "$CONTEXT" -n backseat-driver "$@"; }

# wait_for <description> <timeout seconds> <command...>: poll every 5s until the command succeeds.
wait_for() {
  local description="$1" timeout="$2"
  shift 2
  local deadline=$((SECONDS + timeout))
  until "$@"; do
    if ((SECONDS >= deadline)); then
      echo "::error::timed out after ${timeout}s waiting for: ${description}"
      return 1
    fi
    sleep 5
  done
  echo "ok: ${description}"
}

replicas() { kubectl get deploy caption-worker -o jsonpath='{.spec.replicas}'; }
scaled_up() { (($(replicas) >= 3)); }
scaled_down() { (($(replicas) == 1)); }
all_captioned() {
  local done_scenes
  done_scenes=$(curl -fsS "${API_URL}/jobs/${JOB_ID}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["completed_scenes"])')
  echo "captioned ${done_scenes}/${SCENES}"
  ((done_scenes == SCENES))
}

# The API answers /ready before the tables exist, and db-init may need a few retries while Postgres starts, so
# creating a job before it has completed fails with a 500 (relation "jobs" does not exist).
wait_for "db-init created the tables" 180 kubectl wait job/db-init --for=condition=complete --timeout=5s
wait_for "KEDA reports the caption-worker ScaledObject ready" 120 \
  kubectl wait scaledobject/caption-worker --for=condition=Ready --timeout=5s
wait_for "caption-worker idle at its minimum of 1 replica" 120 scaled_down

# The job only gives the injected captions a row to be recorded against; its own ingest task has no dataset to read.
JOB_ID=$(curl -fsS -X POST "${API_URL}/jobs" -H 'content-type: application/json' -d '{}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "job ${JOB_ID}: queueing ${SCENES} captions"

kubectl exec -i deploy/caption-worker -- env JOB_ID="$JOB_ID" SCENES="$SCENES" python - <<'PY'
import os
from pathlib import Path
from uuid import UUID

from backseat_driver.config import Settings
from backseat_driver.read.s3.factory import build_dataset_store
from backseat_driver.transport.celery_job_queue import CeleryJobQueue
from backseat_driver.models import CaptionTask, SceneKeyframe

settings = Settings()
store = build_dataset_store(settings)
key = "samples/CAM_FRONT/ci.jpg"
store.upload(key, Path("/etc/hostname"))  # any readable file: the stub model never looks at the image
queue = CeleryJobQueue(settings.rabbitmq_url)
for i in range(int(os.environ["SCENES"])):
    keyframe = SceneKeyframe(
        scene_token=f"ci-{i}",
        scene_name=f"ci-scene-{i}",
        camera_channel="CAM_FRONT",
        image_path=key,
    )
    task = CaptionTask(
        job_id=UUID(os.environ["JOB_ID"]), transaction_id="ci-scaling", keyframe=keyframe, image_uri=store.uri_for(key)
    )
    queue.enqueue_caption(task)
PY

wait_for "caption-worker scaled up to at least 3 replicas" 300 scaled_up
wait_for "every queued caption recorded" 300 all_captioned
wait_for "caption-worker scaled back down to 1 replica" 300 scaled_down
