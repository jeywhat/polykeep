"""Filesystem scan + indexation.

Walks ``/storage`` looking for supported 3D files, upserts them into
the DB, marks missing files, lazily computes SHA-256 hashes, extracts thumbnails
and applies auto-tags. Designed to be safely re-runnable: only new
or changed files trigger work.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, FileTag, Tag
from .hasher import sha256_of
from .lys_parser import extract_thumbnail
from .mesh_renderer import can_render, render_mesh
from .paths import storage_root, to_rel
from .stl_renderer import render_stl
from .tagger import extract_tags

# Skip these directories during the scan (trash, hidden dirs).
_SKIP_DIRS = {".trash", "$RECYCLE.BIN", "System Volume Information", "__pycache__"}


@dataclass(frozen=True)
class _ExtraTask:
    file_id: int
    path: Path
    ext: str
    compute_hash: bool
    compute_thumbnail: bool


@dataclass(frozen=True)
class _ExtraResult:
    file_id: int
    hash: str | None = None
    thumbnail_path: str | None = None


def _ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _file_created(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _set_tags(db: File, tag_names: list[str], source: str, session: Session) -> None:
    """Replace the file's tags of ``source`` with ``tag_names``."""
    # Remove existing auto/manual tags of this source.
    for ft in list(db.tags):
        if ft.tag and ft.tag.source == source:
            session.delete(ft)
    for name in tag_names:
        tag = session.query(Tag).filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name, source=source)
            session.add(tag)
            session.flush()
        # Avoid duplicates.
        already = any(ft.tag_id == tag.id for ft in db.tags)
        if not already:
            db.tags.append(FileTag(file=db, tag=tag))


def scan_storage(session: Session) -> dict:
    """Scan /storage and update the index. Returns a summary dict.

    This function uses a SHORT-LIVED session for DB operations only.
    Heavy work (hashing, thumbnail generation) runs in parallel OUTSIDE
    the DB session to avoid locking the database.
    """
    start = time.perf_counter()
    root = storage_root()

    SUPPORTED_EXT = {ext.strip().lower() for ext in settings.supported_extensions.split(",") if ext.strip()}

    found_rel: set[str] = set()
    extra_tasks: list[_ExtraTask] = []
    scanned = added = updated = missing = 0

    # Phase 1: Fast DB pass - find files, create DB entries, collect work
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXT:
            continue
        # Skip anything inside a skipped directory.
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue

        rel = to_rel(path)
        found_rel.add(rel)
        scanned += 1

        stat = path.stat()
        existing = session.query(File).filter_by(rel_path=rel).first()

        if existing is None:
            # relative_to(root) yields "." for files at the storage root;
            # normalise to "" so the whole app treats "" as "root" consistently.
            parent_dir = path.parent.relative_to(root).as_posix()
            if parent_dir == ".":
                parent_dir = ""
            file_obj = File(
                rel_path=rel,
                name=path.name,
                parent_dir=parent_dir,
                ext=_ext(path),
                size=stat.st_size,
                status="unsorted",
                file_created=dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc),
            )
            session.add(file_obj)
            session.flush()  # Get the ID
            extra_tasks.append(_make_extra_task(file_obj, path))
            _set_tags(
                file_obj,
                extract_tags(file_obj.name, file_obj.parent_dir),
                "auto",
                session,
            )
            added += 1
        else:
            changed = False
            if existing.size != stat.st_size:
                existing.size = stat.st_size
                changed = True
            if existing.status == "missing":
                existing.status = "unsorted"
                changed = True
            # Re-extract thumbnail / hash if the size changed.
            if changed:
                extra_tasks.append(_make_extra_task(existing, path, force=True))
                updated += 1
            existing.scanned_at = dt.datetime.now(dt.timezone.utc)

    # Phase 2: Mark missing files
    for db_file in session.query(File).all():
        if db_file.rel_path not in found_rel and db_file.status != "deleted":
            db_file.status = "missing"
            missing += 1

    # Commit the fast DB changes NOW, before heavy work
    session.commit()

    # Phase 3: Heavy work OUTSIDE any DB session (parallel, no locks)
    extra_results = _run_extra_tasks(extra_tasks)

    # Phase 4: Apply results with a FRESH short session
    from ..database import SessionLocal
    apply_session = SessionLocal()
    try:
        _apply_extra_results(apply_session, extra_results)
        apply_session.commit()
    finally:
        apply_session.close()

    duration_ms = int((time.perf_counter() - start) * 1000)
    return {
        "scanned": scanned,
        "added": added,
        "updated": updated,
        "missing": missing,
        "duration_ms": duration_ms,
    }


def _make_extra_task(file_obj: File, path: Path, force: bool = False) -> _ExtraTask:
    """Build a filesystem-only indexing task for work that can run in parallel."""
    return _ExtraTask(
        file_id=file_obj.id,
        path=path,
        ext=file_obj.ext,
        compute_hash=file_obj.ext == "stl" and (force or not file_obj.hash),
        compute_thumbnail=force or not file_obj.thumbnail_path,
    )


def _scan_workers(task_count: int) -> int:
    if task_count <= 1:
        return 1
    configured = settings.scan_workers
    if configured > 0:
        return min(configured, task_count)
    cpu_count = os.cpu_count() or 1
    return min(task_count, max(2, min(cpu_count, 8)))


def _run_extra_tasks(tasks: list[_ExtraTask]) -> list[_ExtraResult]:
    """Run hash / thumbnail work outside SQLAlchemy so sessions stay serial."""
    if not tasks:
        return []

    workers = _scan_workers(len(tasks))
    if workers <= 1:
        return [_index_extras(task) for task in tasks]

    results: list[_ExtraResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan-extra") as pool:
        future_map = {pool.submit(_index_extras, task): task for task in tasks}
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                results.append(future.result())
            except Exception:  # noqa: BLE001 - one bad file must not kill a scan
                results.append(_ExtraResult(file_id=task.file_id))
    return results


def _apply_extra_results(session: Session, results: list[_ExtraResult]) -> None:
    for result in results:
        file_obj = session.get(File, result.file_id)
        if file_obj is None:
            continue
        if result.hash:
            file_obj.hash = result.hash
        if result.thumbnail_path:
            file_obj.thumbnail_path = result.thumbnail_path


def _index_extras(task: _ExtraTask) -> _ExtraResult:
    """Compute hash (STL) and thumbnail (STL + LYS) for a file.

    Hashing is only done for STL files; ``.lys`` are ZIP archives whose hash is
    less useful for de-dup detection (the embedded metadata differs), so we
    skip them to save time.

    Thumbnails:
      * ``.lys`` → extract the embedded preview image (when present).
      * ``.stl`` → render a centred PNG on the CPU (matplotlib, no GPU).
    Both are stored under ``/config/thumbnails/<id>.png`` so the same preview
    route serves either type.
    """
    hash_value: str | None = None
    thumbnail_path: str | None = None

    # Hash
    if task.compute_hash:
        try:
            hash_value = sha256_of(task.path)
        except OSError:
            pass

    # Thumbnail (LYS: embedded image, STL/OBJ/PLY/GLTF/etc: rendered PNG).
    if task.compute_thumbnail:
        thumb_path = settings.thumbnail_dir / f"{task.file_id}.png"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        ok = False
        if task.ext == "lys":
            ok = extract_thumbnail(task.path, thumb_path)
        elif can_render(task.ext):
            ok = render_mesh(task.path, thumb_path)
        if ok:
            thumbnail_path = f"{task.file_id}.png"

    return _ExtraResult(
        file_id=task.file_id,
        hash=hash_value,
        thumbnail_path=thumbnail_path,
    )
