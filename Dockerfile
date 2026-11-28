# ==============================================================================
# Stage 1: Build Frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci

COPY src/frontend/ ./
RUN npm run build

# ==============================================================================
# Stage 2: Install Python dependencies into /opt/venv
FROM python:3.13-slim AS backend-builder

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src/__init__.py ./src/__init__.py
COPY src/backend ./src/backend

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# ==============================================================================
# Stage 3: Lightweight Runtime
FROM python:3.13-slim AS runtime

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=backend-builder /opt/venv /opt/venv
COPY src/__init__.py ./src/__init__.py
COPY src/backend ./src/backend
COPY --from=frontend-builder /frontend/dist ./src/frontend/dist

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    MIA_DATA_DIR=/app/data \
    SQLALCHEMY_ECHO=false

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" || exit 1

CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]