# =============================================================
# Hydraulic Filter Expert Platform — Production Dockerfile
# =============================================================
# Multi-stage build:
#   Stage 1: Build the React frontend
#   Stage 2: Python production image with pre-downloaded ML model
#
# The vector store (2.2GB) is NOT baked in — it's mounted as a
# read-only volume at runtime via docker-compose.
# =============================================================

# -----------------------------------------------------------
# Stage 1: Frontend Builder
# -----------------------------------------------------------
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install dependencies first (layer caching)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# Copy source and build
COPY frontend/ ./
RUN npm run build


# -----------------------------------------------------------
# Stage 2: Production Image
# -----------------------------------------------------------
FROM python:3.12-slim

# System dependencies:
#   build-essential — C compiler for numpy/sentence-transformers wheels
#   curl            — for Docker health checks
#   sqlite3         — for backup.sh (online backup API)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer caching — only rebuilds when requirements change)
# Root requirements.txt: KB dependencies (chromadb, sentence-transformers, openai, bm25, etc.)
# Backend requirements.txt: web framework, database, LLM client
COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt -r /app/backend/requirements.txt

# Pre-download the cross-encoder model (~80MB) so first request isn't slow.
# This caches it to ~/.cache/huggingface/ inside the image.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy knowledge-base Python modules (needed for imports: config, hybrid_search, verified_query, etc.)
# We copy the whole directory minus source-files (excluded by .dockerignore)
COPY ai/02-knowledge-base/ /app/ai/02-knowledge-base/

# Copy backend source
COPY backend/*.py /app/backend/

# Copy built frontend from stage 1
COPY --from=frontend-builder /build/dist/ /app/frontend/dist/

# Create directories for volume mount points
# (these will be overridden by docker-compose volumes, but exist as fallbacks)
RUN mkdir -p /app/vector-store /app/data /app/ai/08-training-data

# The backend runs from /app/backend/ and uses Path(__file__).parent.parent
# to resolve /app/ as PROJECT_ROOT. This gives it access to:
#   /app/vector-store/    (ChromaDB + BM25 index)
#   /app/data/            (SQLite community.db)
#   /app/frontend/dist/   (React build)
#   /app/ai/02-knowledge-base/ (config, hybrid_search, etc.)
#   /app/ai/08-training-data/  (training exhaust JSONL)
WORKDIR /app/backend

EXPOSE 8000

# Health check — FastAPI health endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Single worker: BM25 index is ~263MB in-memory + cross-encoder ~200MB + ChromaDB.
# With streaming responses, one worker handles concurrent requests fine.
# Two workers would double the ~1.5GB memory footprint unnecessarily.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
