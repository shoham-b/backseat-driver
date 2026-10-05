# Production overlay on a real cluster

The `kind` job proves the base manifests and the autoscaling. `deploy/production` is only schema-validated in CI, since
it expects external Postgres, RabbitMQ and S3, real hostnames, and an ingress controller. Run this against a staging
cluster that has them.

Prerequisites: the release PR has been merged, so the image tags in `deploy/production/kustomization.yaml` point at the
new version and those images exist on the registry.

## 1. Apply

1. Replace every `example.com` host and `REPLACE-ME` value, and create the two Secrets described in
   [Deployment](../docs/deployment.md#production).
2. Check what will be applied:

   ```bash
   kubectl kustomize deploy/production | kubectl apply --dry-run=server -f -
   ```

3. Apply it: `kubectl apply -k deploy/production`.

Good looks like: `kubectl -n backseat-driver rollout status` succeeds for `api`, `caption-worker` and `ui`, and no pod
restarts repeatedly.

## 2. Work flows through it

Copy the dataset into the bucket (`backseat-driver dataset upload`), then submit a job:

```bash
kubectl apply -f deploy/k8s/examples/run-job.yaml
```

Good looks like: the job reaches `completed`, `GET /jobs/{id}/descriptions` has one entry per scene, and the UI shows the
results through the ingress.

## 3. Production-only behaviour

| Check | Good looks like |
|---|---|
| Ingress | API and UI answer on their public hostnames over TLS; the UI's live card reaches the API |
| NetworkPolicy | Traffic the policy allows works; a pod outside it cannot reach the workers or the database |
| PodDisruptionBudget | `kubectl drain` of one node keeps the API available |
| Secrets | No credentials appear in the ConfigMap or in `kubectl describe` output |
| Caption worker shutdown | Delete a worker pod mid-caption: the caption finishes (120 s grace) and is not lost |
| Scale up | Queue a large job: KEDA adds caption workers, then removes them when the queue drains |
| Cold start | A fresh caption worker pod becomes ready; note how long the model download takes |

Remove the staging deployment afterwards (`kubectl delete -k deploy/production`).
