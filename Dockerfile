FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

# Install project
COPY . .
RUN uv sync --no-dev

# Install Playwright browsers (Chromium only for slim image)
RUN uv run playwright install chromium --with-deps || true

# --- Runtime stage ---
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libasound2 libportaudio2 curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r omnicore && useradd -r -g omnicore -d /app -s /sbin/nologin omnicore

WORKDIR /app

# Copy virtualenv and project from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

# Ensure non-root user owns the data directory
RUN mkdir -p /app/data /app/workspace/skills && chown -R omnicore:omnicore /app

USER omnicore

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || curl -f http://localhost:8080/api/status || exit 1

CMD ["python", "-m", "scripts.run", "--mode", "rest"]
