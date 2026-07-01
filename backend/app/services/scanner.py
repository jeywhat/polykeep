"""Filesystem scan + indexation.

Walks ``/storage`` looking for ``.stl`` and ``.lys`` files, upserts them into
the DB, marks missing files, lazily computes SHA-256 hashes, extracts ``.lys``
thumbnails and applies auto-tags. Designed to be safely re-runnable: only new
or changed files trigger work.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, FileTag, Tag
from .hasher import sha256_of
from .lys_parser import extract_thumbnail
from .paths import storage_root, to_rel
from .stl_renderer import render_stl
from .tagger import extract_tags

SUPPORTED_EXT = {".stl", ".lys"}

# Skip these directories during the scan (trash, hidden dirs).
_SKIP_DIRS = {".trash", "$RECYCLE.BIN", "System Volume Information", "__pycache__"}


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
    """Scan /storage and update the index. Returns a summary dict."""
    start = time.perf_counter()
    root = storage_root()

    found_rel: set[str] = set()
    scanned = added = updated = missing = 0

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
            file_obj = File(
                rel_path=rel,
                name=path.name,
                parent_dir=path.parent.relative_to(root).as_posix(),
                ext=_ext(path),
                size=stat.st_size,
                status="unsorted",
                file_created=dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc),
            )
            session.add(file_obj)
            session.flush()
            _index_extras(file_obj, path, session)
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
                _index_extras(existing, path, session, force=True)
                updated += 1
            existing.scanned_at = dt.datetime.now(dt.timezone.utc)

    # Mark files that vanished from disk.
    for db_file in session.query(File).all():
        if db_file.rel_path not in found_rel and db_file.status != "deleted":
            db_file.status = "missing"
            missing += 1

    session.commit()

    duration_ms = int((time.perf_counter() - start) * 1000)
    return {
        "scanned": scanned,
        "added": added,
        "updated": updated,
        "missing": missing,
        "duration_ms": duration_ms,
    }


def _index_extras(
    file_obj: File, path: Path, session: Session, force: bool = False
) -> None:
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
    # Hash
    if file_obj.ext == "stl" and (force or not file_obj.hash):
        try:
            file_obj.hash = sha256_of(path)
        except OSError:
            pass

    # Thumbnail (LYS: embedded image, STL: rendered PNG).
    if force or not file_obj.thumbnail_path:
        thumb_path = settings.thumbnail_dir / f"{file_obj.id or 'tmp'}.png"
        ok = False
        if file_obj.ext == "lys":
            ok = extract_thumbnail(path, thumb_path)
        elif file_obj.ext == "stl":
            ok = render_stl(path, thumb_path)
        if ok:
            file_obj.thumbnail_path = f"{file_obj.id}.png"
