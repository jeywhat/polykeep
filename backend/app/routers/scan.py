"""Scan router — triggers filesystem indexing + progress tracking."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ScanResultOut
from ..services import scanner, sorter
from ..services.scan_progress import (
    ScanInProgressError,
    ScanPhase,
    complete_scan,
    get_progress,
    update_phase,
)

router = APIRouter()
_scan_request_lock = threading.Lock()


@router.post("/scan", response_model=ScanResultOut)
def trigger_scan(db: Session = Depends(get_db)):
    """Scan /storage, index files, then refresh sort suggestions."""
    if not _scan_request_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Un scan est deja en cours")
    try:
        try:
            result = scanner.scan_storage(db, finalize=False)
        except ScanInProgressError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # Recompute suggestions while the scan lock is still held.
        update_phase("default", ScanPhase.SUGGESTIONS, 0, phase_total_files=0)
        try:
            sorter.compute_suggestions(db)
        except Exception as exc:  # noqa: BLE001
            # Suggestions are best-effort; never fail the whole scan for them.
            result["suggestions_error"] = str(exc)
        update_phase("default", ScanPhase.SUGGESTIONS, 100)
        complete_scan("default")
        return result
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Scan échoué : {exc}") from exc
    finally:
        _scan_request_lock.release()


@router.get("/scan/progress")
def scan_progress():
    """Return current scan progress (phase, percentage, files processed)."""
    prog = get_progress()
    return {
        "phase": prog.phase.value,
        "phase_progress": round(prog.phase_progress, 1),
        "overall_progress": round(prog.overall_progress, 1),
        "total_files": prog.total_files,
        "processed_files": prog.processed_files,
        "phase_total_files": prog.phase_total_files,
        "current_file": prog.current_file,
        "elapsed_seconds": round(prog.elapsed_seconds, 1),
        "eta_seconds": round(prog.eta_seconds, 1) if prog.eta_seconds else None,
        "error": prog.error_message,
    }
