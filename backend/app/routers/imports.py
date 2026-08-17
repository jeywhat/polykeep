"""Endpoints for discovering and importing files from configured folders."""
from __future__ import annotations

import threading
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ImportFileOut, ImportRequest, ImportResultOut, WatchDirsOut
from ..models import File as LibraryFile
from ..services import importer, scanner
from ..services.paths import to_rel

router = APIRouter()
_import_lock = threading.Lock()


@router.get("/imports/config", response_model=WatchDirsOut)
def get_config(db: Session = Depends(get_db)):
    return {"paths": [str(path) for path in importer.watch_dirs(db)]}


@router.put("/imports/config", response_model=WatchDirsOut)
def put_config(payload: WatchDirsOut, db: Session = Depends(get_db)):
    try:
        return {"paths": importer.save_watch_dirs(db, payload.paths)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/imports", response_model=list[ImportFileOut])
def list_imports(db: Session = Depends(get_db)):
    try:
        return importer.discover(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports", response_model=ImportResultOut)
def do_import(payload: ImportRequest, db: Session = Depends(get_db)):
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un import est déjà en cours")
    try:
        imported, skipped = importer.import_files(db, payload.source_paths, payload.mode)
        result = scanner.scan_storage(db)
        return {"imported": imported, "skipped": skipped, "scan": result, "errors": []}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import échoué : {exc}") from exc
    finally:
        _import_lock.release()


@router.post("/imports/upload", response_model=ImportResultOut)
async def upload_imports(
    files: list[UploadFile] = File(...),
    manifest: str = Form(...),
    db: Session = Depends(get_db),
):
    """Receive browser dropped files and import each one independently."""
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un import est déjà en cours")
    try:
        try:
            entries = json.loads(manifest)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Aperçu d’import invalide") from exc
        imported = 0
        errors: list[str] = []
        successful: list[tuple[object, dict]] = []
        if len(files) != len(entries):
            raise HTTPException(status_code=400, detail="Fichiers et aperçu désynchronisés")
        for upload, entry in zip(files, entries):
            try:
                destination = await importer.write_upload(upload, entry, db)
                if destination is None:
                    errors.append(f"{upload.filename}: fichier déjà présent ou invalide")
                else:
                    imported += 1
                    successful.append((destination, entry))
            except Exception as exc:  # noqa: BLE001 - continue the batch
                errors.append(f"{upload.filename}: {exc}")
            finally:
                await upload.close()
        scan = scanner.scan_storage(db)
        for destination, entry in successful:
            file_obj = db.query(LibraryFile).filter_by(rel_path=to_rel(destination)).first()
            tags = entry.get("tags", []) if isinstance(entry, dict) else []
            if file_obj is not None and isinstance(tags, list):
                scanner._set_tags(file_obj, [str(tag) for tag in tags if str(tag).strip()], "manual", db)
        db.commit()
        return {"imported": imported, "skipped": 0, "scan": scan, "errors": errors}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import échoué : {exc}") from exc
    finally:
        _import_lock.release()
