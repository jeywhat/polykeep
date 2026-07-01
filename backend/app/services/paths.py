"""Path safety helpers.

Every filesystem operation on user-supplied paths MUST go through ``safe_join``.
It guarantees the resolved path stays inside the storage root, blocking path
traversal attacks (``../../etc/passwd`` and friends).
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings


class UnsafePathError(ValueError):
    """Raised when a resolved path escapes the storage root."""


def storage_root() -> Path:
    root = settings.storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_join(*parts: str) -> Path:
    """Join ``parts`` onto the storage root and assert the result stays inside.

    Accepts relative POSIX paths (forward slashes). Returns an absolute Path.
    Raises ``UnsafePathError`` if the target resolves outside /storage.
    """
    root = storage_root()
    combined = Path(*parts) if parts else Path()
    # Re-anchor any absolute-looking input to the root.
    target = (root / combined).resolve()
    if root not in (target, *target.parents):
        raise UnsafePathError(f"Path escapes storage root: {target}")
    return target


def to_rel(abs_path: Path) -> str:
    """Convert an absolute path inside /storage to a POSIX relative string."""
    root = storage_root()
    return abs_path.resolve().relative_to(root).as_posix()
