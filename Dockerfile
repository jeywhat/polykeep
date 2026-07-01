# syntax=docker/dockerfile:1
#
# PolyKeep — single-container image for Unraid.
#
# Stage 1 builds the React frontend, stage 2 installs the Python backend and
# serves the built frontend as static files on the same port (8000).
# Build context = project root (so both frontend/ and backend/ are available).

# ---------------- Stage 1: build the frontend ----------------
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
# Install deps first (cached layer).
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
# Build → output goes to /backend/static (see vite.config.js outDir).
COPY frontend/ ./
RUN npm run build

# ---------------- Stage 2: runtime (Python) ----------------
FROM python:3.12-slim AS runtime
WORKDIR /app

# Keep the image lean.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

# The FastAPI app serves the frontend from backend/static/.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Copy the built frontend into the location the app expects.
COPY --from=frontend-build /backend/static ./static

# Default volume mount points (override at runtime for Unraid).
ENV T3D_CONFIG_DIR=/config \
    T3D_STORAGE_DIR=/storage

# Pre-create the mount dirs so permissions are predictable.
RUN mkdir -p /config /storage

EXPOSE 8000

# uvicorn with a single worker is plenty for a personal organiser.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
