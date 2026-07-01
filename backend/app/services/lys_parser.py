"""Lychee Slicer ``.lys`` thumbnail extraction.

The ``.lys`` format is proprietary and undocumented. Empirically many Lychee
project files are ZIP containers that embed a preview image (PNG/JPEG) among
other resources. This module attempts to find and extract that preview. If the
file is not a ZIP or contains no recognisable image, it returns ``None`` — we
never raise on an unreadable ``.lys`` because the rest of the app must keep
working.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

# Names/patterns commonly used for the embedded preview image.
_PREVIEW_HINTS = ("thumbnail", "preview", "thumb", "screenshot", "image")
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def extract_thumbnail(lys_path: Path, out_path: Path) -> bool:
    """Try to extract a preview image from a ``.lys`` file.

    Returns ``True`` on success (``out_path`` written), ``False`` otherwise.
    """
    try:
        if not zipfile.is_zipfile(lys_path):
            return False
        with zipfile.ZipFile(lys_path) as zf:
            candidates = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.lower()
                if name.endswith(_IMAGE_EXTS):
                    # Prefer entries whose name hints at a preview.
                    score = 2 if any(h in name for h in _PREVIEW_HINTS) else 1
                    # Prefer PNG, then JPEG.
                    if name.endswith(".png"):
                        score += 0.5
                    candidates.append((score, info))
            if not candidates:
                return False
            candidates.sort(key=lambda c: c[0], reverse=True)
            best = candidates[0][1]
            data = zf.read(best)
            out_path.write_bytes(data)
            return True
    except (zipfile.BadZipFile, OSError, KeyError):
        return False
