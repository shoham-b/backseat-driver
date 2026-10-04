#!/usr/bin/env bash
# Autoscaling check for the kind CI cluster (.github/workflows/kind.yml): load the caption queue, then expect KEDA
# to scale the caption workers up, every caption to be recorded, and the workers to scale back down.
#
# Captions are injected straight onto the queue from the API pod (using the project's own CeleryJobQueue) because
# the CI cluster has no nuScenes dataset for the ingest worker to fan out.
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

wait_for "KEDA reports the caption-worker ScaledObject ready" 120 \
  kubectl wait scaledobject/caption-worker --for=condition=Ready --timeout=5s
wait_for "caption-worker idle at its minimum of 1 replica" 120 scaled_down

# The job only gives the injected captions a row to be recorded against; its own ingest task has no dataset to read.
JOB_ID=$(curl -fsS -X POST "${API_URL}/jobs" -H 'content-type: application/json' -d '{}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "job ${JOB_ID}: queueing ${SCENES} captions"

kubectl exec -i deploy/api -- env JOB_ID="$JOB_ID" SCENES="$SCENES" python - <<'PY'
import os
from uuid import UUID

from backseat_driver.jobs.celery_job_queue import CeleryJobQueue
from backseat_driver.models import CaptionTask, SceneKeyframe

queue = CeleryJobQueue(os.environ["BACKSEAT_DRIVER_RABBITMQ_URL"])
for i in range(int(os.environ["SCENES"])):
    keyframe = SceneKeyframe(
        scene_token=f"ci-{i}",
        scene_name=f"ci-scene-{i}",
        camera_channel="CAM_FRONT",
        image_path="/etc/hostname",  # any readable file: the stub model never looks at the image
    )
    queue.enqueue_caption(CaptionTask(job_id=UUID(os.environ["JOB_ID"]), transaction_id="ci-scaling", keyframe=keyframe))
PY

wait_for "caption-worker scaled up to at least 3 replicas" 300 scaled_up
wait_for "every queued caption recorded" 300 all_captioned
wait_for "caption-worker scaled back down to 1 replica" 300 scaled_down
