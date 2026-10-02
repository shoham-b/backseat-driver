# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# ── Stage 1: uv + Python base ─────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS build-tools
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy

# ── Stage 2: Build CLI dependencies (the batch pipeline) ──────────────────────
FROM build-tools AS build-cli
WORKDIR /app
# Pass 1: external deps only — cached as long as lock + pyproject unchanged
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-backseat-driver-cli \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group cli
# Pass 2: install project source — only invalidated when source changes
COPY backseat_driver/ backseat_driver/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-backseat-driver-cli \
    uv sync --frozen --group cli

# ── Stage 3: Build API dependencies ───────────────────────────────────────────
FROM build-tools AS build-api
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-backseat-driver-api \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group api
COPY backseat_driver/ backseat_driver/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-backseat-driver-api \
    uv sync --frozen --group api

# ── Stage 4: CLI runtime — the pipeline itself ─────────────────────────────────
# nuscenes-devkit pulls in opencv-python, which needs libGL/libglib at runtime
# even though this pipeline never renders anything.
FROM python:${PYTHON_VERSION}-slim AS cli
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build-cli /app/.venv /app/.venv
COPY --from=build-cli /app/backseat_driver /app/backseat_driver

# Non-root so the image runs under Kubernetes' runAsNonRoot; HF_HOME is where the model weights are cached.
# The cache dir exists up front so a fresh named volume mounted on it (compose's hf-cache) inherits app ownership.
RUN useradd --system --uid 10001 --create-home app \
    && install -d -o app -g app /home/app/.cache/huggingface
USER 10001
ENV PATH=/app/.venv/bin:$PATH \
    HF_HOME=/home/app/.cache/huggingface
ENTRYPOINT ["backseat-driver"]
CMD ["run"]

# ── Stage 5: API runtime ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS api
WORKDIR /app
COPY --from=build-api /app/.venv /app/.venv
COPY --from=build-api /app/backseat_driver /app/backseat_driver

RUN useradd --system --uid 10001 --create-home app
USER 10001
ENV PATH=/app/.venv/bin:$PATH \
    HF_HOME=/home/app/.cache/huggingface
EXPOSE 8080
CMD ["fastapi", "run", "backseat_driver/api/app.py", "--host", "0.0.0.0", "--port", "8080"]
