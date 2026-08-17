"""Scan progress tracking for real-time progress updates."""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class ScanPhase(str, Enum):
    IDLE = "idle"
    DISCOVERY = "discovery"          # Phase 1: filesystem traversal
    DB_UPSERT = "db_upsert"          # Phase 2: bulk DB operations
    MISSING_MARK = "missing_mark"    # Phase 3: mark missing files
    THUMBNAILS = "thumbnails"        # Phase 4: hash/thumbnail generation
    APPLY_RESULTS = "apply_results"  # Phase 5: apply results
    SUGGESTIONS = "suggestions"      # Phase 6: recompute sort suggestions
    COMPLETE = "complete"
    ERROR = "error"


class ScanInProgressError(RuntimeError):
    """Raised when a scan is already running in this application process."""


@dataclass
class ScanProgress:
    phase: ScanPhase = ScanPhase.IDLE
    phase_progress: float = 0.0      # 0-100 within current phase
    total_files: int = 0
    processed_files: int = 0
    phase_total_files: int = 0
    current_file: str = ""
    start_time: float = 0.0
    error_message: Optional[str] = None

    @property
    def overall_progress(self) -> float:
        """Overall progress 0-100 across all phases."""
        phase_bounds = {
            ScanPhase.IDLE: (0.0, 0.0),
            ScanPhase.DISCOVERY: (0.0, 10.0),
            ScanPhase.DB_UPSERT: (10.0, 20.0),
            ScanPhase.MISSING_MARK: (20.0, 25.0),
            ScanPhase.THUMBNAILS: (25.0, 85.0),
            ScanPhase.APPLY_RESULTS: (85.0, 95.0),
            ScanPhase.SUGGESTIONS: (95.0, 100.0),
            ScanPhase.COMPLETE: (100.0, 100.0),
            ScanPhase.ERROR: (0.0, 0.0),
        }
        start, end = phase_bounds.get(self.phase, (0.0, 0.0))
        return start + (end - start) * self.phase_progress / 100.0

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time if self.start_time > 0 else 0

    @property
    def eta_seconds(self) -> Optional[float]:
        if self.overall_progress <= 0 or self.overall_progress >= 100:
            return None
        elapsed = self.elapsed_seconds
        return (elapsed / self.overall_progress) * (100 - self.overall_progress)


# Process-local state for progress (one active scan at a time).
_progress_store: dict[str, ScanProgress] = {}
_lock = threading.Lock()
_scan_lock = threading.Lock()
_active_scan_id: str | None = None


def get_progress(scan_id: str = "default") -> ScanProgress:
    """Get or create progress tracker for a scan."""
    with _lock:
        if scan_id not in _progress_store:
            _progress_store[scan_id] = ScanProgress()
        # Never expose the mutable object while another thread is updating it.
        return replace(_progress_store[scan_id])


def start_scan(scan_id: str = "default") -> ScanProgress:
    """Initialize progress for a new scan."""
    global _active_scan_id

    if not _scan_lock.acquire(blocking=False):
        raise ScanInProgressError("Un scan est deja en cours")
    with _lock:
        prog = ScanProgress(
            phase=ScanPhase.DISCOVERY,
            start_time=time.time(),
        )
        _progress_store[scan_id] = prog
        _active_scan_id = scan_id
        return prog


def update_phase(scan_id: str, phase: ScanPhase, progress: float = 0.0, **kwargs) -> None:
    """Update scan phase and sub-progress."""
    with _lock:
        prog = _progress_store.get(scan_id)
        if prog:
            prog.phase = phase
            prog.phase_progress = max(0.0, min(100.0, progress))
            for k, v in kwargs.items():
                if hasattr(prog, k):
                    setattr(prog, k, v)


def update_file_progress(scan_id: str, processed: int, total: int, current: str = "") -> None:
    """Update file-level progress within current phase."""
    with _lock:
        prog = _progress_store.get(scan_id)
        if prog:
            prog.processed_files = processed
            prog.phase_total_files = total
            prog.current_file = current
            if total > 0:
                prog.phase_progress = (processed / total) * 100


def complete_scan(scan_id: str = "default") -> None:
    """Mark scan as complete."""
    global _active_scan_id

    release_lock = False
    with _lock:
        prog = _progress_store.get(scan_id)
        if prog:
            prog.phase = ScanPhase.COMPLETE
            prog.phase_progress = 100.0
            prog.phase_total_files = prog.total_files
            prog.processed_files = prog.total_files
        if _active_scan_id == scan_id:
            _active_scan_id = None
            release_lock = True
    if release_lock:
        _scan_lock.release()


def error_scan(scan_id: str, error: str) -> None:
    """Mark scan as errored."""
    global _active_scan_id

    release_lock = False
    with _lock:
        prog = _progress_store.get(scan_id)
        if prog:
            prog.phase = ScanPhase.ERROR
            prog.error_message = error
        if _active_scan_id == scan_id:
            _active_scan_id = None
            release_lock = True
    if release_lock:
        _scan_lock.release()


def reset_progress(scan_id: str = "default") -> None:
    """Reset progress to idle."""
    with _lock:
        _progress_store[scan_id] = ScanProgress()


@contextmanager
def mutation_lock() -> Iterator[None]:
    """Serialize filesystem/suggestion mutations with the active scan."""
    if not _scan_lock.acquire(blocking=False):
        raise ScanInProgressError("Un scan est deja en cours")
    try:
        yield
    finally:
        _scan_lock.release()
