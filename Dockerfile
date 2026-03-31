# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install into an isolated prefix — no system pollution
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --prefix=/deps -r requirements.txt


# ── Stage 2: lean runtime ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: non-root user
RUN groupadd --gid 1001 appgroup \
 && useradd --uid 1001 --gid 1001 -m appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /deps /usr/local

# Copy application source
COPY --chown=appuser:appgroup \
     main.py agent.py config.py logger.py ./

USER appuser

# Cloud Run injects PORT automatically; default to 8080
ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Prefer gunicorn + uvicorn workers in production for concurrency
CMD exec gunicorn main:app \
        --workers 2 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "0.0.0.0:${PORT}" \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -