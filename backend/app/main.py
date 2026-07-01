"""FastAPI application entrypoint.

Serves the JSON API under ``/api`` and, when the frontend has been built, the
static React bundle at the root (so a single container exposes everything on
one port — ideal for Unraid).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import get_db, init_db
from .routers import files, preview, scan, sort

app = FastAPI(title="PolyKeep", version="1.0.0")

# Permissive CORS — local dev Vite runs on :5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router, prefix="/api", tags=["scan"])
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(sort.router, prefix="/api", tags=["sort"])
app.include_router(preview.router, prefix="/api", tags=["preview"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    db = next(get_db())
    try:
        from .models import File

        count = db.query(File).count()
    finally:
        db.close()
    return {
        "status": "ok",
        "storage_dir": str(settings.storage_dir),
        "file_count": count,
    }


# --- Serve the built frontend (SPA fallback) -------------------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "name": "PolyKeep API",
            "note": "Frontend not built yet. Run the API directly or build the "
            "frontend and copy it to backend/static/.",
            "docs": "/docs",
            "health": "/api/health",
        }
    )


# Mount static assets (js/css chunks) if the frontend was built.
if FRONTEND_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIR / "assets"),
        name="assets",
    )
