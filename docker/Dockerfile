# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# ── Stage 1: uv + Python base ─────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS build-tools
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy

# ── Stage 2: Build CLI dependencies (the batch pipeline) ──────────────────────
FROM build-tools AS build-cli
WORKDIR /app
# Pass 1: external deps only — cached as long as lock + pyproject unchanged
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm-scene-description-cli \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group cli
# Pass 2: install project source — only invalidated when source changes
COPY vlmscene/ vlmscene/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm-scene-description-cli \
    uv sync --frozen --group cli

# ── Stage 3: Build API dependencies ───────────────────────────────────────────
FROM build-tools AS build-api
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm-scene-description-api \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group api
COPY vlmscene/ vlmscene/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm-scene-description-api \
    uv sync --frozen --group api

# ── Stage 4: CLI runtime — the pipeline itself ─────────────────────────────────
# nuscenes-devkit pulls in opencv-python, which needs libGL/libglib at runtime
# even though this pipeline never renders anything.
FROM python:${PYTHON_VERSION}-slim AS cli
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build-cli /app/.venv /app/.venv
COPY --from=build-cli /app/vlmscene /app/vlmscene

ENV PATH=/app/.venv/bin:$PATH
ENTRYPOINT ["vlm-scene-description"]
CMD ["run"]

# ── Stage 5: API runtime ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS api
WORKDIR /app
COPY --from=build-api /app/.venv /app/.venv
COPY --from=build-api /app/vlmscene /app/vlmscene

ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8080
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8080", "vlmscene.api.app:app"]
