# Avatar — single-container image.
# Stage 1 builds the Vite frontend (-> frontend/dist).
# Stage 2 runs the FastAPI backend with uv, serving the built frontend on :8000.
# The .env is NOT baked in; it is passed at runtime (--env-file / Fly secrets).

# ---------------------------------------------------------------------------
# Stage 1: build the static frontend
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build/frontend

# Install dependencies first so this layer caches when only source changes.
COPY frontend/package.json frontend/package-lock.json* frontend/npm-shrinkwrap.json* ./
RUN if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then npm ci; else npm install; fi

# Copy the rest of the frontend and build. The design-system assets are copied
# into frontend/ by the orchestrator before the image build, so the whole
# frontend tree (incl. public/) is present here.
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: backend runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv from its official distroless image (pinned binary, no pip needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    # Use the slim base image's system Python (/usr/local/bin, world-executable)
    # rather than letting uv download a managed interpreter into /root, which is
    # mode 700 and therefore unreadable once the container drops to USER appuser
    # (the venv's python shebang would fail with "Permission denied").
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12

# Mirror the repo layout so config.py's parents[2] resolves to /app and finds
# /app/knowledge and /app/.env (if mounted) at runtime.
WORKDIR /app

# Install backend dependencies first (cached unless the lockfile changes).
COPY backend/pyproject.toml backend/uv.lock backend/.python-version /app/backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --project /app/backend

# Application code.
COPY backend/ /app/backend/

# Knowledge files (system prompt + FAQ) must be in the image so the prompt and
# avatars load at runtime.
COPY knowledge/ /app/knowledge/

# Built frontend from stage 1.
COPY --from=frontend /build/frontend/dist /app/frontend/dist

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/backend/.venv/bin:${PATH}"

EXPOSE 8000

WORKDIR /app/backend

# Serve the API + static frontend. --app-dir . makes `app` importable.
# PORT is honoured (Fly sets it to 8000) but defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir ."]
