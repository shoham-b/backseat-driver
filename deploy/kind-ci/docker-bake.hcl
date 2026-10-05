# The images the `kind` CI job deploys, built together so the builds run concurrently. The `cli` image is left out:
# the CI overlay doesn't use it (see kustomization.yaml). Each target keeps its own cache scope so they don't evict
# one another.
variable "PYTHON_VERSION" {
  default = "3.14"
}

target "base" {
  context    = "."
  dockerfile = "docker/Dockerfile"
  args       = { PYTHON_VERSION = PYTHON_VERSION }
}

target "api" {
  inherits   = ["base"]
  target     = "api"
  tags       = ["backseat-driver-api:local"]
  cache-from = ["type=gha,scope=kind-api"]
  cache-to   = ["type=gha,scope=kind-api,mode=max"]
}

target "ingest-worker" {
  inherits   = ["base"]
  target     = "ingest-worker"
  tags       = ["backseat-driver-ingest-worker:local"]
  cache-from = ["type=gha,scope=kind-ingest-worker"]
  cache-to   = ["type=gha,scope=kind-ingest-worker,mode=max"]
}

target "caption-worker" {
  inherits   = ["base"]
  target     = "caption-worker"
  tags       = ["backseat-driver-caption-worker:local"]
  cache-from = ["type=gha,scope=kind-caption-worker"]
  cache-to   = ["type=gha,scope=kind-caption-worker,mode=max"]
}

group "default" {
  targets = ["api", "ingest-worker", "caption-worker"]
}
