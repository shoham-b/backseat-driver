# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13

# ── Stage 1: uv + Python base ─────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS build-tools
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy

# ── Stage 2: Build API dependencies ───────────────────────────────────────────
FROM build-tools AS build-api
WORKDIR /app
# Pass 1: external deps only — cached as long as lock + pyproject unchanged
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm_scene_description-api \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group api
# Pass 2: install project source — only invalidated when source changes
COPY vlm_scene_description/ vlm_scene_description/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-vlm_scene_description-api \
    uv sync --frozen --group api

# ── Stage 4: API runtime ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS api
WORKDIR /app
COPY --from=build-api /app/.venv /app/.venv
COPY --from=build-api /app/vlm_scene_description /app/vlm_scene_description

ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8080
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8080", "vlm_scene_description.api.app:app"]

