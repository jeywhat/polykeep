"""Sort engine: compute suggestions + execute them safely.

All sorting happens in two phases:
  1. ``compute_suggestions`` analyses the DB and creates ``Suggestion`` rows
     (status ``pending``). Nothing on disk changes.
  2. ``apply_suggestion`` performs the filesystem move only when the user
     confirms. It is the ONLY place that relocates/deletes files.

Suggestion payload shapes (JSON):
  - type 'duplicate': {"file_ids": [...], "keep_id": int, "reason": str}
        apply => soft-delete the non-keep files (move to /storage/.trash).
  - type 'group':     {"file_ids": [...], "folder": str}
        apply => create /storage/<folder> and move the files in.
  - type 'move':      {"file_id": int, "target_dir": str}
        apply => move the single file to target_dir.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, Suggestion
from .grouper import group_by_prefix, group_by_similarity, suggested_group_name
from .paths import safe_join, storage_root, to_rel


# ---------------------------------------------------------------------------
# Computing suggestions
# ---------------------------------------------------------------------------

def _existing_pending(session: Session, stype: str, payload: dict) -> Suggestion | None:
    """Return a pending suggestion with the same payload, if any."""
    target = json.dumps(payload, sort_keys=True)
    for s in session.query(Suggestion).filter_by(type=stype, status="pending"):
        if json.dumps(json.loads(s.payload), sort_keys=True) == target:
            return s
    return None


def compute_suggestions(session: Session) -> dict:
    """Wipe stale pending suggestions and recompute from the current index."""
    # Clear old pending suggestions (a fresh scan invalidates them).
    session.query(Suggestion).filter_by(status="pending").delete()
    session.commit()

    files = session.query(File).filter(File.status.in_(["unsorted", "sorted"])).all()

    created = 0
    created += _detect_duplicates(session, files)
    created += _detect_groups(session, files)

    session.commit()
    return {"suggestions_created": created}


def _detect_duplicates(session: Session, files: list[File]) -> int:
    """Group STL files by hash; identical hashes => duplicate suggestion."""
    count = 0
    by_hash: dict[str, list[File]] = defaultdict(list)
    for f in files:
        if f.ext == "stl" and f.hash:
            by_hash[f.hash].append(f)

    for hash_val, group in by_hash.items():
        if len(group) < 2:
            continue
        # Keep the first (lowest id), suggest deleting the rest.
        group.sort(key=lambda f: f.id)
        keep = group[0]
        others = group[1:]
        payload = {
            "file_ids": [f.id for f in group],
            "keep_id": keep.id,
            "reason": f"Hash identique (SHA-256) — {len(group)} fichiers",
            "hash": hash_val,
        }
        if _existing_pending(session, "duplicate", payload) is None:
            session.add(
                Suggestion(type="duplicate", payload=json.dumps(payload))
            )
            count += 1
    return count


def _detect_groups(session: Session, files: list[File]) -> int:
    """Propose grouping isolated files that share a name pattern."""
    count = 0
    # Only consider files sitting directly in /storage (loose) — those benefit
    # most from being grouped into a folder.
    loose = [f for f in files if f.parent_dir == ""]

    # Strategy 1: common prefix token.
    names = {f.id: f.name for f in loose}
    clusters = group_by_prefix(names)
    used: set[int] = set()
    for cluster_ids in clusters:
        members = [f for f in loose if f.id in cluster_ids]
        folder = suggested_group_name([f.name for f in members])
        payload = {
            "file_ids": [f.id for f in members],
            "folder": folder,
            "reason": f"Préfixe de nom commun : « {folder} »",
        }
        if _existing_pending(session, "group", payload) is None:
            session.add(Suggestion(type="group", payload=json.dumps(payload)))
            count += 1
            used.update(cluster_ids)

    # Strategy 2: similarity for the remaining loose files.
    remaining = {fid: names[fid] for fid in names if fid not in used}
    for cluster_ids in group_by_similarity(remaining):
        members = [f for f in loose if f.id in cluster_ids]
        folder = suggested_group_name([f.name for f in members])
        payload = {
            "file_ids": [f.id for f in members],
            "folder": folder,
            "reason": f"Noms similaires (groupe « {folder} »)",
        }
        if _existing_pending(session, "group", payload) is None:
            session.add(Suggestion(type="group", payload=json.dumps(payload)))
            count += 1
    return count


# ---------------------------------------------------------------------------
# Applying suggestions
# ---------------------------------------------------------------------------

def apply_suggestion(session: Session, suggestion_id: int) -> dict:
    s = session.get(Suggestion, suggestion_id)
    if s is None:
        raise ValueError("Suggestion introuvable")
    if s.status != "pending":
        raise ValueError(f"Suggestion déjà {s.status}")

    payload = json.loads(s.payload)
    if s.type == "duplicate":
        result = _apply_duplicate(session, payload)
    elif s.type == "group":
        result = _apply_group(session, payload)
    elif s.type == "move":
        result = _apply_move(session, payload)
    else:
        raise ValueError(f"Type inconnu : {s.type}")

    s.status = "applied"
    s.applied_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return {"applied": s.type, "detail": result}


def _apply_duplicate(session: Session, payload: dict) -> dict:
    keep_id = payload["keep_id"]
    file_ids = payload["file_ids"]
    deleted: list[str] = []
    for fid in file_ids:
        if fid == keep_id:
            continue
        f = session.get(File, fid)
        if f and f.status not in ("deleted", "missing"):
            move_to_trash(session, f)
            deleted.append(f.name)
    return {"deleted_to_trash": deleted, "kept_id": keep_id}


def _apply_group(session: Session, payload: dict) -> dict:
    folder = payload["folder"]
    file_ids = payload["file_ids"]
    moved: list[str] = []
    target = safe_join(folder)
    target.mkdir(parents=True, exist_ok=True)
    for fid in file_ids:
        f = session.get(File, fid)
        if f and f.status not in ("deleted", "missing"):
            move_file(session, f, target)
            moved.append(f.name)
    return {"moved_to": folder, "files": moved}


def _apply_move(session: Session, payload: dict) -> dict:
    f = session.get(File, payload["file_id"])
    if not f:
        raise ValueError("Fichier introuvable")
    target = safe_join(payload["target_dir"])
    target.mkdir(parents=True, exist_ok=True)
    move_file(session, f, target)
    return {"moved_to": payload["target_dir"], "file": f.name}


# ---------------------------------------------------------------------------
# File move primitives (the only place disk is mutated)
# ---------------------------------------------------------------------------

def move_file(session: Session, f: File, target_dir: Path) -> None:
    """Move ``f`` into ``target_dir`` (must be inside /storage)."""
    src = safe_join(f.rel_path)
    if not src.exists():
        f.status = "missing"
        return
    dst = target_dir / f.name
    # Avoid clobbering an existing file.
    if dst.exists():
        stem, suffix = dst.stem, dst.suffix
        i = 1
        while dst.exists():
            dst = target_dir / f"{stem}_{i}{suffix}"
            i += 1
    shutil.move(str(src), str(dst))
    f.rel_path = to_rel(dst)
    parent_dir = dst.parent.relative_to(storage_root()).as_posix()
    f.parent_dir = "" if parent_dir == "." else parent_dir
    f.status = "sorted"


def move_to_trash(session: Session, f: File) -> None:
    """Soft-delete: move the file into /storage/.trash/<date>/."""
    src = safe_join(f.rel_path)
    if not src.exists():
        f.status = "missing"
        return
    date_tag = dt.datetime.now().strftime("%Y-%m-%d")
    trash_dir = safe_join(settings.trash_subdir, date_tag, f.parent_dir)
    trash_dir.mkdir(parents=True, exist_ok=True)
    dst = trash_dir / f.name
    if dst.exists():
        dst = trash_dir / f"{f.stem}_{int(dt.datetime.now().timestamp())}{f.suffix}"
    shutil.move(str(src), str(dst))
    f.status = "deleted"
    f.rel_path = to_rel(dst)


def hard_delete(session: Session, f: File) -> None:
    """Permanently remove a file already in the trash."""
    src = safe_join(f.rel_path)
    if src.exists():
        src.unlink()
    session.delete(f)
