# Stage 1: Build React Frontend
FROM node:24-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Hardened Python Production Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# Install backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user and persistent storage directory
RUN useradd -m -u 1000 sentinel && \
    mkdir -p /app/backend/data && \
    chown -R sentinel:sentinel /app

# Copy application source code
COPY --chown=sentinel:sentinel backend/ backend/
COPY --chown=sentinel:sentinel patterns/ patterns/
COPY --chown=sentinel:sentinel scripts/ scripts/

# Copy compiled frontend assets from builder stage
COPY --from=frontend-builder --chown=sentinel:sentinel /build/dist /app/frontend/dist

USER sentinel

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/api/health/live' % os.getenv('PORT','8000'))" || exit 1

CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
