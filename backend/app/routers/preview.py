"""Preview router — stream STL binaries + serve extracted LYS thumbnails + generic model files."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import File
from ..services.paths import safe_join

router = APIRouter()


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
    return FileResponse(path, media_type=media, filename=f.name)


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
    return FileResponse(path, media_type=media, filename=f.name)


@router.get("/preview/lys/{file_id}")
def serve_lys_thumbnail(file_id: int, db: Session = Depends(get_db)):
    """Serve the previously-extracted LYS preview image."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    if not f.thumbnail_path:
        raise HTTPException(status_code=404, detail="Aucune vignette pour ce .lys")
    from ..config import settings

    thumb = settings.thumbnail_dir / f.thumbnail_path
    if not thumb.is_file():
        raise HTTPException(status_code=404, detail="Vignette manquante sur disque")
    media = "image/png" if thumb.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(thumb, media_type=media)


@router.get("/preview/thumb/{file_id}")
def serve_thumbnail(file_id: int, db: Session = Depends(get_db)):
    """Serve a file's thumbnail (rendered STL PNG or extracted LYS image)."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    if not f.thumbnail_path:
        raise HTTPException(status_code=404, detail="Aucune vignette pour ce fichier")
    from ..config import settings

    thumb = settings.thumbnail_dir / f.thumbnail_path
    if not thumb.is_file():
        raise HTTPException(status_code=404, detail="Vignette manquante sur disque")
    media = "image/png" if thumb.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(thumb, media_type=media)
