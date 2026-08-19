"""Preview router — stream STL binaries + serve extracted LYS thumbnails + generic model files."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import File
from ..config import settings
from ..services.mesh_renderer import can_render, convert_to_glb
from ..services.paths import safe_join

router = APIRouter()


def _thumbnail_path(file_obj: File):
    """Return only this file's canonical, non-empty thumbnail."""
    expected = f"{file_obj.id}.png"
    if file_obj.thumbnail_path != expected:
        return None
    thumbnail = settings.thumbnail_dir / expected
    try:
        return thumbnail if thumbnail.is_file() and thumbnail.stat().st_size > 0 else None
    except OSError:
        return None


def _thumbnail_media_type(path) -> str:
    """Detect common embedded image formats even when the cache is named .png."""
    try:
        with path.open("rb") as image:
            header = image.read(12)
    except OSError:
        header = b""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"BM"):
        return "image/bmp"
    return "image/png"


@router.get("/preview/stl/{file_id}")
def stream_stl(file_id: int, db: Session = Depends(get_db)):
    """Stream the raw STL so the browser can parse it with Three.js."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    path = safe_join(f.rel_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Fichier absent du disque")
    media = "model/stl" if f.ext == "stl" else "application/octet-stream"
    return FileResponse(
        path,
        media_type=media,
        filename=f.name,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/preview/model/{file_id}")
def stream_model(file_id: int, db: Session = Depends(get_db)):
    """Stream any 3D model file for the Three.js viewer."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    path = safe_join(f.rel_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Fichier absent du disque")

    # MIME types for common 3D formats
    mime_map = {
        "stl": "model/stl",
        "obj": "model/obj",
        "ply": "application/octet-stream",
        "gltf": "model/gltf+json",
        "glb": "model/gltf-binary",
        "dae": "model/vnd.collada+xml",
        "fbx": "application/octet-stream",
        "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    }
    media = mime_map.get(f.ext, "application/octet-stream")
    return FileResponse(
        path,
        media_type=media,
        filename=f.name,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/preview/glb/{file_id}")
def preview_glb(file_id: int, db: Session = Depends(get_db)):
    """Convert a source mesh once and serve its browser-friendly GLB cache."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    if not can_render(f.ext):
        raise HTTPException(status_code=404, detail="Format non convertible en GLB")
    source = safe_join(f.rel_path)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Fichier absent ou conversion impossible")
    cached = settings.thumbnail_dir / "glb" / f"{f.id}.glb"
    if not convert_to_glb(source, cached):
        raise HTTPException(status_code=404, detail="Conversion GLB impossible")
    return FileResponse(cached, media_type="model/gltf-binary", filename=f"{f.id}.glb")


@router.get("/preview/lys/{file_id}")
def serve_lys_thumbnail(file_id: int, db: Session = Depends(get_db)):
    """Serve the previously-extracted LYS preview image."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    thumb = _thumbnail_path(f)
    if thumb is None:
        raise HTTPException(status_code=404, detail="Aucune vignette pour ce .lys")
    return FileResponse(
        thumb,
        media_type=_thumbnail_media_type(thumb),
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/preview/thumb/{file_id}")
def serve_thumbnail(file_id: int, db: Session = Depends(get_db)):
    """Serve a file's thumbnail (rendered STL PNG or extracted LYS image)."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    thumb = _thumbnail_path(f)
    if thumb is None:
        raise HTTPException(status_code=404, detail="Aucune vignette pour ce fichier")
    return FileResponse(
        thumb,
        media_type=_thumbnail_media_type(thumb),
        headers={"Cache-Control": "no-cache"},
    )
