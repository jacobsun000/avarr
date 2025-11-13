# syntax=docker/dockerfile:1.7

FROM node:20-bullseye-slim AS web-build
WORKDIR /app/web

ENV PNPM_HOME=/root/.local/share/pnpm
ENV PATH="${PNPM_HOME}:${PATH}"
RUN corepack enable

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm build


FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl git ca-certificates build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY api /app/api
COPY --from=web-build /app/web/dist ./webui/dist

RUN mkdir -p /app/downloads /app/api/storage

ENV VIRTUAL_ENV=/app/api/.venv \
    PATH="/app/api/.venv/bin:${PATH}" \
    AVARR_DOWNLOAD_ROOT=/app/downloads \
    AVARR_DATABASE_URL=sqlite:///./storage/storage.db \
    AVARR_ALLOWED_SOURCE_DOMAINS= \
    AVARR_BASE_EXTERNAL_URL= \
    AVARR_TELEGRAM_BOT_TOKEN= \
    AVARR_TELEGRAM_WEBHOOK_SECRET= \
    AVARR_NOTIFIER_MIN_PERCENT_STEP=10 \
    PORT=8000

VOLUME ["/app/downloads", "/app/api/storage"]

EXPOSE 8000

CMD ["uvicorn", "avarr.app:app", "--host", "0.0.0.0", "--port", "8000"]
