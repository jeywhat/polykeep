"""Sort router — list / apply / reject suggestions, recompute them."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Suggestion
from ..schemas import SuggestionOut
from ..services import sorter

router = APIRouter()


@router.get("/suggestions")
def list_suggestions(
    status: str = "pending", db: Session = Depends(get_db)
) -> list[SuggestionOut]:
    query = db.query(Suggestion)
    if status and status != "all":
        query = query.filter(Suggestion.status == status)
    rows = query.order_by(Suggestion.created_at.desc()).all()
    return [SuggestionOut.from_model(s) for s in rows]


@router.post("/suggestions/recompute")
def recompute(db: Session = Depends(get_db)) -> dict:
    """Reanalyse the index and refresh pending suggestions."""
    return sorter.compute_suggestions(db)


@router.post("/suggestions/{suggestion_id}/apply")
def apply_suggestion(suggestion_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return sorter.apply_suggestion(db, suggestion_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(suggestion_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.get(Suggestion, suggestion_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Suggestion introuvable")
    s.status = "rejected"
    db.commit()
    return {"rejected": suggestion_id}
