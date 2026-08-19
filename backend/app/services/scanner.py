"""Filesystem scan + indexation.

Walks ``/storage`` looking for supported 3D files, upserts them into
the DB, marks missing files, lazily computes SHA-256 hashes, extracts thumbnails
and applies auto-tags. Designed to be safely re-runnable: only new
or changed files trigger work.

Optimizations:
- os.scandir() iterative traversal
- batched ORM queries for existing files
- top-level directory parallelization for filesystem discovery
"""
from __future__ import annotations

import datetime as dt
import gc
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session

from ..config import settings
from ..models import File, FileTag, Tag
from .hasher import sha256_of
from .fingerprint import compute_fingerprint, compute_fingerprint_mesh
from .lys_parser import extract_thumbnail
from .mesh_renderer import can_render, load_mesh, render_mesh_mesh
from .paths import storage_root
from .scan_progress import (
    ScanStoppedError,
    ScanPhase,
    complete_scan,
    checkpoint,
    error_scan,
    stop_scan,
    start_scan,
    update_file_progress,
    update_phase,
)
from .tagger import extract_tags


_MESH_TASK_LIMIT = threading.Semaphore(max(1, settings.mesh_workers))
_LOGGER = logging.getLogger(__name__)

# Skip these directories during the scan (trash, hidden dirs).
_SKIP_DIRS = {".trash", "$RECYCLE.BIN", "System Volume Information", "__pycache__"}
_SQL_BATCH_SIZE = 500


class _DiscoveryError(RuntimeError):
    """Raised when the filesystem cannot be scanned completely."""


@dataclass(frozen=True)
class _ExtraTask:
    file_id: int
    path: Path
    ext: str
    compute_hash: bool
    compute_fingerprint: bool
    compute_thumbnail: bool
    source_size: int | None = None
    source_mtime_ns: int | None = None


@dataclass(frozen=True)
class _ExtraResult:
    file_id: int
    hash: str | None = None
    fingerprint: str | None = None
    thumbnail_path: str | None = None


@dataclass(frozen=True)
class _FileInfo:
    """Lightweight file info collected from scandir."""
    rel_path: str
    name: str
    parent_dir: str
    ext: str
    size: int
    mtime: float
    full_path: Path
    mtime_ns: int = 0


def _file_info(
    entry: os.DirEntry[str], relative_root: Path, supported_ext: set[str]
) -> _FileInfo | None:
    """Build file metadata for a directory entry when its extension is supported."""
    suffix = Path(entry.name).suffix.lower().lstrip(".")
    if suffix not in supported_ext:
        return None

    try:
        stat = entry.stat()
        full = Path(entry.path)
        rel = full.relative_to(relative_root).as_posix()
        parent = full.parent.relative_to(relative_root).as_posix()
    except (OSError, ValueError) as exc:
        raise _DiscoveryError(f"Impossible de lire {entry.path}: {exc}") from exc
    if parent == ".":
        parent = ""
    return _FileInfo(
        rel_path=rel,
        name=entry.name,
        parent_dir=parent,
        ext=suffix,
        size=stat.st_size,
        mtime=stat.st_mtime,
        full_path=full,
        mtime_ns=stat.st_mtime_ns,
    )


def _iter_direct_files(
    root: Path, supported_ext: set[str], relative_root: Path
) -> Iterator[_FileInfo]:
    """Yield supported files directly inside ``root`` without descending."""
    try:
        with os.scandir(root) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        info = _file_info(entry, relative_root, supported_ext)
                        if info is not None:
                            yield info
                except (OSError, ValueError) as exc:
                    raise _DiscoveryError(f"Impossible de lire {entry.path}: {exc}") from exc
    except (PermissionError, OSError) as exc:
        raise _DiscoveryError(f"Impossible de parcourir {root}: {exc}") from exc


def _iter_files(
    root: Path, supported_ext: set[str], relative_root: Path | None = None
) -> Iterator[_FileInfo]:
    """Iterate supported files using os.scandir - no Path allocation per file.

    Yields _FileInfo with all data needed for DB operations.
    """
    root = root.resolve()
    relative_root = (relative_root or root).resolve()
    skip_dirs = _SKIP_DIRS

    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in skip_dirs:
                                stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            info = _file_info(entry, relative_root, supported_ext)
                            if info is not None:
                                yield info
                    except (PermissionError, OSError, ValueError) as exc:
                        raise _DiscoveryError(f"Impossible de lire {entry.path}: {exc}") from exc
        except (PermissionError, OSError) as exc:
            raise _DiscoveryError(f"Impossible de parcourir {current}: {exc}") from exc


def _iter_files_parallel(root: Path, supported_ext: set[str], max_workers: int = 4) -> Iterator[_FileInfo]:
    """Parallel top-level directory scan."""
    root = root.resolve()
    skip_dirs = _SKIP_DIRS

    # Get top-level directories
    top_dirs: list[Path] = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and entry.name not in skip_dirs:
                    top_dirs.append(Path(entry.path))
    except (PermissionError, OSError) as exc:
        raise _DiscoveryError(f"Impossible de parcourir {root}: {exc}") from exc

    # Scan each top-level directory once, while handling root-level files here.
    def scan_one(dir_path: Path) -> list[_FileInfo]:
        return list(_iter_files(dir_path, supported_ext, root))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(scan_one, directory) for directory in top_dirs]
        for info in _iter_direct_files(root, supported_ext, root):
            yield info
        for future in as_completed(futures):
            for info in future.result():
                yield info


def _set_tags(db: File, tag_names: list[str], source: str, session: Session) -> None:
    """Replace the file's tags of ``source`` with ``tag_names``."""
    for ft in list(db.tags):
        if ft.tag and ft.tag.source == source:
            session.delete(ft)
    for name in tag_names:
        tag = session.query(Tag).filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name, source=source)
            session.add(tag)
            session.flush()
        already = any(ft.tag_id == tag.id for ft in db.tags)
        if not already:
            db.tags.append(FileTag(file=db, tag=tag))


def _mtime_matches(file_obj: File, mtime: float) -> bool:
    """Compare a stored filesystem timestamp with the current one."""
    if file_obj.file_created is None:
        return False
    stored = file_obj.file_created
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=dt.timezone.utc)
    return abs(stored.timestamp() - mtime) <= 0.001


def _thumbnail_exists(file_obj: File) -> bool:
    expected = f"{file_obj.id}.png"
    if file_obj.thumbnail_path != expected:
        return False
    try:
        relative = Path(file_obj.thumbnail_path)
        if relative.is_absolute() or ".." in relative.parts:
            return False
        thumbnail = settings.thumbnail_dir / relative
        return thumbnail.is_file() and thumbnail.stat().st_size > 0
    except OSError:
        return False


def _needs_extra_work(file_obj: File) -> bool:
    needs_hash = file_obj.ext == "stl" and not file_obj.hash
    needs_fingerprint = _fingerprint_allowed(file_obj) and can_render(file_obj.ext) and not file_obj.fingerprint
    needs_thumbnail = (
        _thumbnail_allowed(file_obj)
        and (file_obj.ext == "lys" or can_render(file_obj.ext))
    ) and not _thumbnail_exists(file_obj)
    return needs_hash or needs_fingerprint or needs_thumbnail


def _thumbnail_allowed(file_obj: File) -> bool:
    return file_obj.size <= settings.thumbnail_max_size_mb * 1024 * 1024


def _fingerprint_allowed(file_obj: File) -> bool:
    return file_obj.size <= settings.fingerprint_max_size_mb * 1024 * 1024


def scan_storage(
    session: Session, scan_id: str = "default", finalize: bool = True
) -> dict:
    """Scan /storage and update the index. Returns a summary dict.

    This function uses a SHORT-LIVED session for DB operations only.
    Heavy work (hashing, thumbnail generation) runs in parallel OUTSIDE
    the DB session to avoid locking the database.

    Progress is tracked via scan_progress module (accessible via /api/scan/progress).
    When ``finalize`` is false, the caller keeps the scan active while it performs
    follow-up work such as suggestion computation.
    """
    start_scan(scan_id)
    start = time.perf_counter()

    try:
        root = storage_root()
        supported_ext = {
            ext.strip().lower().lstrip(".")
            for ext in settings.supported_extensions.split(",")
            if ext.strip()
        }

        found_rel: set[str] = set()
        extra_tasks: list[_ExtraTask] = []
        scanned = added = updated = missing = 0

        # Phase 1: Fast filesystem pass - collect all file info (no DB yet)
        update_phase(scan_id, ScanPhase.DISCOVERY, 0)
        # Collect first so progress can expose a stable total to the client.
        file_infos = list(
            {
                info.rel_path: info
                for info in _iter_files_parallel(root, supported_ext, max_workers=4)
            }.values()
        )
        total_files = len(file_infos)
        update_phase(
            scan_id,
            ScanPhase.DISCOVERY,
            100,
            total_files=total_files,
            processed_files=total_files,
            phase_total_files=total_files,
        )

        # Phase 2: Batched DB upsert — flush + commit + expunge per batch so
        # the session identity map never holds more than _SQL_BATCH_SIZE ORM
        # objects at once, even with 50 000+ files in the library.
        update_phase(
            scan_id,
            ScanPhase.DB_UPSERT,
            0,
            total_files=total_files,
            processed_files=0,
            phase_total_files=total_files,
        )
        scanned = len(file_infos)
        now_utc = dt.datetime.now(dt.timezone.utc)

        for batch_offset in range(0, len(file_infos), _SQL_BATCH_SIZE):
            checkpoint(scan_id)
            batch = file_infos[batch_offset : batch_offset + _SQL_BATCH_SIZE]

            # Query existing files for THIS batch only — keeps identity map flat.
            existing_by_rel: dict[str, File] = {
                f.rel_path: f
                for f in session.query(File)
                .filter(File.rel_path.in_([fi.rel_path for fi in batch]))
                .all()
            }

            new_by_rel: dict[str, File] = {}
            batch_tag_tasks: list[tuple[str, File, _FileInfo]] = []

            for i, info in enumerate(batch):
                update_file_progress(
                    scan_id, batch_offset + i + 1, total_files, info.rel_path
                )
                found_rel.add(info.rel_path)
                existing = existing_by_rel.get(info.rel_path)

                if existing is None:
                    file_obj = File(
                        rel_path=info.rel_path,
                        name=info.name,
                        parent_dir=info.parent_dir,
                        ext=info.ext,
                        size=info.size,
                        status="unsorted",
                        file_created=dt.datetime.fromtimestamp(info.mtime, dt.timezone.utc),
                    )
                    new_by_rel[info.rel_path] = file_obj
                    batch_tag_tasks.append(("new", file_obj, info))
                    added += 1
                else:
                    changed = existing.size != info.size or not _mtime_matches(existing, info.mtime)
                    if changed:
                        existing.size = info.size
                        existing.file_created = dt.datetime.fromtimestamp(
                            info.mtime, dt.timezone.utc
                        )
                        existing.hash = None
                        existing.fingerprint = None
                        existing.thumbnail_path = None
                    if existing.status == "missing":
                        existing.status = "unsorted"
                        changed = True
                    if changed or _needs_extra_work(existing):
                        if not _thumbnail_exists(existing):
                            existing.thumbnail_path = None
                        batch_tag_tasks.append(("existing", existing, info))
                    if changed:
                        updated += 1
                    existing.scanned_at = now_utc

            # Flush new files so they get IDs before tag processing.
            if new_by_rel:
                session.add_all(list(new_by_rel.values()))
                session.flush()

            # Process tags + collect extra tasks for this batch only.
            # All ORM attribute reads happen BEFORE commit, so there is no
            # DetachedInstanceError risk after expunge.
            for kind, file_obj, info in batch_tag_tasks:
                if kind == "new":
                    _set_tags(
                        file_obj,
                        extract_tags(file_obj.name, file_obj.parent_dir),
                        "auto",
                        session,
                    )
                extra_tasks.append(
                    _make_extra_task(
                        file_obj,
                        info.full_path,
                        force=kind == "existing",
                        info=info,
                    )
                )

            # Commit this batch (durability) then release all ORM objects.
            session.flush()
            session.commit()
            session.expunge_all()

        # Phase 3: Mark missing files without loading every row into the ORM.
        update_phase(
            scan_id,
            ScanPhase.MISSING_MARK,
            0,
            total_files=total_files,
            processed_files=0,
            phase_total_files=0,
        )
        missing_rows = (
            session.query(File.id, File.rel_path)
            .filter(
                File.status != "deleted",
                File.status != "missing",
            )
            .yield_per(_SQL_BATCH_SIZE)
        )
        missing_ids = [file_id for file_id, rel_path in missing_rows if rel_path not in found_rel]
        for offset in range(0, len(missing_ids), _SQL_BATCH_SIZE):
            checkpoint(scan_id)
            session.query(File).filter(
                File.id.in_(missing_ids[offset : offset + _SQL_BATCH_SIZE])
            ).update({"status": "missing"}, synchronize_session=False)
        missing = len(missing_ids)
        update_phase(scan_id, ScanPhase.MISSING_MARK, 100)

        # Commit the fast DB changes NOW, before heavy work
        session.commit()

        # Release scan-scope data structures before the memory-heavy mesh phase.
        del file_infos, missing_rows, found_rel
        gc.collect()

        # Phase 4: Heavy work OUTSIDE any DB session (parallel, no locks)
        update_phase(
            scan_id,
            ScanPhase.THUMBNAILS,
            0,
            total_files=total_files,
            processed_files=0,
            phase_total_files=len(extra_tasks),
        )
        extra_results = _run_extra_tasks(extra_tasks, scan_id)
        if not extra_tasks:
            update_phase(scan_id, ScanPhase.THUMBNAILS, 100)

        # Phase 5: Apply results with a FRESH short session
        update_phase(
            scan_id,
            ScanPhase.APPLY_RESULTS,
            0,
            total_files=total_files,
            processed_files=0,
            phase_total_files=1,
        )
        from ..database import SessionLocal
        apply_session = SessionLocal()
        try:
            _apply_extra_results(apply_session, extra_results)
            apply_session.commit()
        finally:
            apply_session.close()
        update_phase(scan_id, ScanPhase.APPLY_RESULTS, 100, processed_files=1)

        if finalize:
            complete_scan(scan_id)

    except ScanStoppedError:
        session.rollback()
        stop_scan(scan_id)
        return {
            "scanned": scanned,
            "added": added,
            "updated": updated,
            "missing": missing,
            "duration_ms": int((time.perf_counter() - start) * 1000),
        }
    except Exception as e:
        session.rollback()
        error_scan(scan_id, str(e))
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)
    return {
        "scanned": scanned,
        "added": added,
        "updated": updated,
        "missing": missing,
        "duration_ms": duration_ms,
    }


def _make_extra_task(
    file_obj: File,
    path: Path,
    force: bool = False,
    info: _FileInfo | None = None,
) -> _ExtraTask:
    """Build a filesystem-only indexing task for work that can run in parallel."""
    return _ExtraTask(
        file_id=file_obj.id,
        path=path,
        ext=file_obj.ext,
        compute_hash=file_obj.ext == "stl" and (force or not file_obj.hash),
        compute_fingerprint=(
            _fingerprint_allowed(file_obj)
            and can_render(file_obj.ext)
            and (force or not file_obj.fingerprint)
        ),
        compute_thumbnail=_thumbnail_allowed(file_obj) and (force or not _thumbnail_exists(file_obj)),
        source_size=info.size if info is not None else None,
        source_mtime_ns=(
            info.mtime_ns
            if info is not None and info.mtime_ns
            else None
        ),
    )


def _source_matches(task: _ExtraTask) -> bool:
    """Ensure heavy work still targets the bytes discovered by the scan."""
    if task.source_size is None and task.source_mtime_ns is None:
        return True
    try:
        stat = task.path.stat()
    except OSError:
        return False
    if task.source_size is not None and stat.st_size != task.source_size:
        return False
    return (
        task.source_mtime_ns is None
        or abs(stat.st_mtime_ns - task.source_mtime_ns) <= 1_000_000
    )


def _thumbnail_output_path(task: _ExtraTask) -> Path:
    return settings.thumbnail_dir / f"{task.file_id}.png"


def _discard_thumbnail(task: _ExtraTask) -> None:
    """Remove a result that was rendered from bytes changed mid-scan."""
    try:
        _thumbnail_output_path(task).unlink(missing_ok=True)
    except OSError:
        pass


def _scan_workers(task_count: int) -> int:
    if task_count <= 1:
        return 1
    configured = settings.scan_workers
    if configured > 0:
        return min(configured, task_count)
    cpu_count = os.cpu_count() or 1
    return min(task_count, max(2, min(cpu_count, 8)))


def _run_extra_tasks(tasks: list[_ExtraTask], scan_id: str = "default") -> list[_ExtraResult]:
    """Run hash / thumbnail work outside SQLAlchemy so sessions stay serial."""
    if not tasks:
        return []

    workers = _scan_workers(len(tasks))
    update_phase(
        scan_id,
        ScanPhase.THUMBNAILS,
        0,
        phase_total_files=len(tasks),
    )

    if workers <= 1:
        results = []
        for i, task in enumerate(tasks):
            try:
                checkpoint(scan_id)
                results.append(_index_extras(task))
            except ScanStoppedError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad file must not kill a scan
                _LOGGER.warning("Scan extra work failed for %s: %s", task.path, exc)
                results.append(_ExtraResult(file_id=task.file_id))
            if (i + 1) % 32 == 0:
                gc.collect()
            update_file_progress(scan_id, i + 1, len(tasks), task.path.name)
        gc.collect()
        return results

    results: list[_ExtraResult] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan-extra") as pool:
        def run_task(task):
            checkpoint(scan_id)
            return _index_extras(task)

        future_map = {pool.submit(run_task, task): task for task in tasks}
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                results.append(future.result())
            except ScanStoppedError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad file must not kill a scan
                _LOGGER.warning("Scan extra work failed for %s: %s", task.path, exc)
                results.append(_ExtraResult(file_id=task.file_id))
            completed += 1
            update_file_progress(scan_id, completed, len(tasks), task.path.name)
            if completed % 32 == 0:
                gc.collect()
    gc.collect()
    return results


def _apply_extra_results(session: Session, results: list[_ExtraResult]) -> None:
    """Persist extra results with batched core UPDATEs.

    Nothing is loaded into the session's identity map, so memory stays flat
    even when a scan produces hundreds of thousands of results.
    """
    from sqlalchemy import bindparam, update

    table = File.__table__

    def _exec(stmt, rows: list[dict]) -> None:
        for offset in range(0, len(rows), _SQL_BATCH_SIZE):
            session.execute(
                stmt,
                rows[offset : offset + _SQL_BATCH_SIZE],
                execution_options={"synchronize_session": False},
            )

    hashes = [{"file_id": r.file_id, "hash": r.hash} for r in results if r.hash]
    fingerprints = [
        {"file_id": r.file_id, "fingerprint": r.fingerprint}
        for r in results
        if r.fingerprint
    ]
    thumbnails = [
        {"file_id": r.file_id, "thumbnail_path": f"{r.file_id}.png"}
        for r in results
        if r.thumbnail_path == f"{r.file_id}.png"
    ]
    if hashes:
        _exec(
            update(table)
            .where(table.c.id == bindparam("file_id"))
            .values(hash=bindparam("hash")),
            hashes,
        )
    if fingerprints:
        _exec(
            update(table)
            .where(table.c.id == bindparam("file_id"))
            .values(fingerprint=bindparam("fingerprint")),
            fingerprints,
        )
    if thumbnails:
        _exec(
            update(table)
            .where(table.c.id == bindparam("file_id"))
            .values(thumbnail_path=bindparam("thumbnail_path")),
            thumbnails,
        )


def _index_extras(task: _ExtraTask) -> _ExtraResult:
    """Compute hash, geometry fingerprint and thumbnail for a file.

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
    fingerprint: str | None = None

    if not _source_matches(task):
        _LOGGER.warning("Skipping %s: source changed during scan", task.path)
        return _ExtraResult(file_id=task.file_id)

    # Hash — streaming, cheap, runs on all scan workers.
    if task.compute_hash:
        try:
            hash_value = sha256_of(task.path)
        except OSError:
            pass

    # Mesh work — the memory-heavy part, bounded by the mesh semaphore.
    # The mesh is loaded AT MOST ONCE per file and shared between the
    # fingerprint and the thumbnail, then released immediately.
    if task.compute_fingerprint or (task.compute_thumbnail and task.ext != "lys"):
        with _MESH_TASK_LIMIT:
            if task.compute_fingerprint and not task.compute_thumbnail:
                try:
                    fingerprint = compute_fingerprint(task.path)
                except Exception as exc:  # noqa: BLE001 - thumbnail work is independent
                    _LOGGER.warning("Fingerprint failed for %s: %s", task.path, exc)
            else:
                mesh = None
                try:
                    mesh = load_mesh(task.path)
                    if mesh is not None:
                        if task.compute_fingerprint:
                            try:
                                fingerprint = compute_fingerprint_mesh(mesh)
                            except Exception as exc:  # noqa: BLE001 - do not block rendering
                                _LOGGER.warning("Fingerprint failed for %s: %s", task.path, exc)
                        if task.compute_thumbnail:
                            thumb_path = _thumbnail_output_path(task)
                            thumb_path.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                if render_mesh_mesh(mesh, thumb_path):
                                    thumbnail_path = f"{task.file_id}.png"
                                else:
                                    _LOGGER.debug("Thumbnail renderer returned no image for %s", task.path)
                            except Exception as exc:  # noqa: BLE001 - one mesh must not stop the scan
                                _LOGGER.warning("Thumbnail rendering failed for %s: %s", task.path, exc)
                finally:
                    del mesh

    # LYS thumbnails come from the embedded preview image (no mesh needed).
    if task.compute_thumbnail and task.ext == "lys":
        thumb_path = _thumbnail_output_path(task)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if extract_thumbnail(task.path, thumb_path):
                thumbnail_path = f"{task.file_id}.png"
            else:
                _LOGGER.debug("No embedded thumbnail found in %s", task.path)
        except Exception as exc:  # noqa: BLE001 - one archive must not stop the scan
            _LOGGER.warning("Thumbnail extraction failed for %s: %s", task.path, exc)

    # Never associate bytes that changed while the renderer was working.
    if not _source_matches(task):
        if thumbnail_path:
            _discard_thumbnail(task)
        return _ExtraResult(file_id=task.file_id)

    return _ExtraResult(
        file_id=task.file_id,
        hash=hash_value,
        fingerprint=fingerprint,
        thumbnail_path=thumbnail_path,
    )
