"""Files router — list / detail / move / delete / tag."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import File, FileTag, Tag
from ..schemas import FileListOut, FileOut, MoveRequest, TagRequest
from ..services.paths import safe_join
from ..services.sorter import move_file, move_to_trash

router = APIRouter()


def _file_to_out(f: File) -> FileOut:
    out = FileOut.model_validate(f)
    out.tags = [ft.tag.name for ft in f.tags if ft.tag]
    # Thumbnail URL (works for both rendered STL and extracted LYS images).
    if f.thumbnail_path:
        out.preview_url = f"/api/preview/thumb/{f.id}"
    return out


@router.get("/files", response_model=FileListOut)
def list_files(
    status: str | None = None,
    tag: str | None = None,
    ext: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(File)
    if status:
        query = query.filter(File.status == status)
    if ext:
        query = query.filter(File.ext == ext.lower())
    if tag:
        query = query.join(FileTag, File.tags).join(Tag).filter(Tag.name == tag)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(File.name.ilike(like), File.parent_dir.ilike(like))
        )
    total = query.count()
    items = (
        query.order_by(File.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return FileListOut(
        items=[_file_to_out(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/files/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: Session = Depends(get_db)):
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return _file_to_out(f)


@router.post("/files/{file_id}/move", response_model=FileOut)
def move_one_file(
    file_id: int, req: MoveRequest, db: Session = Depends(get_db)
):
    """Move a single file into target_dir (relative to /storage)."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    try:
        target = safe_join(req.target_dir)
        target.mkdir(parents=True, exist_ok=True)
        move_file(db, f, target)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _file_to_out(f)


@router.post("/files/{file_id}/delete", response_model=FileOut)
def delete_file(file_id: int, db: Session = Depends(get_db)):
    """Soft-delete: move to /storage/.trash (reversible)."""
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    try:
        move_to_trash(db, f)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _file_to_out(f)


@router.post("/files/{file_id}/tags", response_model=FileOut)
def add_tag(file_id: int, req: TagRequest, db: Session = Depends(get_db)):
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    tag = db.query(Tag).filter_by(name=req.tag).first()
    if tag is None:
        tag = Tag(name=req.tag, source=req.source)
        db.add(tag)
        db.flush()
    if not any(ft.tag_id == tag.id for ft in f.tags):
        f.tags.append(FileTag(file=f, tag=tag))
    db.commit()
    return _file_to_out(f)


@router.delete("/files/{file_id}/tags/{tag_name}", response_model=FileOut)
def remove_tag(file_id: int, tag_name: str, db: Session = Depends(get_db)):
    f = db.get(File, file_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    for ft in list(f.tags):
        if ft.tag and ft.tag.name.lower() == tag_name.lower():
            db.delete(ft)
    db.commit()
    return _file_to_out(f)


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    return [{"id": t.id, "name": t.name, "source": t.source, "count": len(t.files)} for t in db.query(Tag).all()]
