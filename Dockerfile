# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# TaxIQ — Multi-stage Dockerfile
#
# Stage 1 (node-builder): Build React frontend → frontend/dist
# Stage 2 (app):          Python backend + built frontend + pre-computed data
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-slim AS node-builder

WORKDIR /build

# Install dependencies first (layer cache)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

# Copy source and build
COPY frontend/ ./
RUN npm run build
# Output: /build/dist/


# ── Stage 2: Python app ───────────────────────────────────────────────────────
FROM python:3.11-slim AS app

# System deps for sentence-transformers / torch (CPU-only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (CPU-only torch to keep image smaller)
COPY requirements.txt ./
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# Copy pre-computed data (chunks + vectors — no indexing needed)
COPY backend/data/chunks_1961.json  ./backend/data/chunks_1961.json
COPY backend/data/chunks_2025.json  ./backend/data/chunks_2025.json
COPY backend/data/vectors_hf_1961.npy ./backend/data/vectors_hf_1961.npy
COPY backend/data/vectors_hf_2025.npy ./backend/data/vectors_hf_2025.npy

# Copy built React frontend from Stage 1
COPY --from=node-builder /build/dist ./frontend/dist

# HuggingFace model cache (persisted via Docker volume)
ENV HF_HOME=/cache/huggingface
ENV TRANSFORMERS_CACHE=/cache/huggingface

# Default config — all overridable via docker-compose env_file
ENV QDRANT_URL=http://qdrant:6333
ENV QDRANT_API_KEY=
ENV LLM_PROVIDER=ollama_cloud
ENV LLM_MODEL=auto
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

EXPOSE 8000

# Health check — waits for FastAPI to be ready
HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
