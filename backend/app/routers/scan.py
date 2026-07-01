"""Scan router — triggers filesystem indexing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ScanResultOut
from ..services import scanner, sorter

router = APIRouter()


@router.post("/scan", response_model=ScanResultOut)
def trigger_scan(db: Session = Depends(get_db)):
    """Scan /storage, index files, then refresh sort suggestions."""
    try:
        result = scanner.scan_storage(db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Scan échoué : {exc}") from exc
    # Recompute suggestions after a fresh scan.
    try:
        sorter.compute_suggestions(db)
    except Exception as exc:  # noqa: BLE001
        # Suggestions are best-effort; never fail the whole scan for them.
        result["suggestions_error"] = str(exc)
    return result
