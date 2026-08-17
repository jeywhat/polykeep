"""Small, deterministic geometry fingerprints for cross-format matching."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


_QUANTUM = 1e-4
_PREFIX_LENGTH = 6  # Three bytes, represented as hexadecimal.
_FACE_OFFSET = _PREFIX_LENGTH
_FACE_LENGTH = 8


def _quantize(value: float) -> int:
    return int(round(float(value) / _QUANTUM))


def _load_mesh(path: Path):
    import trimesh

    # Let trimesh weld duplicate vertices so binary STL and OBJ exports of the
    # same model produce the same connected-component count.
    # Loading directly as one mesh avoids retaining a Scene plus a concatenated
    # copy at the same time.
    loaded = trimesh.load(str(path), force="mesh", process=True)
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if not isinstance(loaded, trimesh.Scene):
        return None
    meshes = [
        geometry
        for geometry in loaded.dump(concatenate=False)
        if isinstance(geometry, trimesh.Trimesh) and len(geometry.faces)
    ]
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


def compute_fingerprint(path: Path) -> str | None:
    """Return a hexadecimal geometry signature, or ``None`` on invalid input.

    The digest prefix is based on normalized geometry only; the face count is
    stored in the following eight hexadecimal characters so the sorter can
    apply its deliberate +/-5% tolerance without loading the mesh again.
    """
    try:
        mesh = _load_mesh(path)
        if mesh is None or len(mesh.faces) == 0 or len(mesh.vertices) == 0:
            return None
        extents = mesh.bounds[1] - mesh.bounds[0]
        scale = float(extents.max())
        if scale <= 0:
            return None
        components = len(mesh.split(only_watertight=False))
        features = {
            "volume": _quantize(mesh.volume / (scale ** 3)),
            "dimensions": [_quantize(item / scale) for item in extents],
            "area": _quantize(mesh.area / (scale ** 2)),
            "components": components,
        }
        canonical = json.dumps(features, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        faces = len(mesh.faces)
        if faces > 0xFFFFFFFF:
            return None
        return f"{digest[:_PREFIX_LENGTH]}{faces:0{_FACE_LENGTH}x}{digest[_PREFIX_LENGTH:]}"
    except (OSError, ValueError, ImportError, TypeError):
        return None


def fingerprint_face_count(value: str) -> int | None:
    """Extract the encoded face count from a fingerprint."""
    if len(value) < _FACE_OFFSET + _FACE_LENGTH:
        return None
    try:
        return int(value[_FACE_OFFSET : _FACE_OFFSET + _FACE_LENGTH], 16)
    except ValueError:
        return None


def fingerprints_match(left: str, right: str) -> bool:
    """Match the strict geometry bucket and a +/-5% face-count tolerance."""
    if left[:_PREFIX_LENGTH] != right[:_PREFIX_LENGTH]:
        return False
    left_faces = fingerprint_face_count(left)
    right_faces = fingerprint_face_count(right)
    if not left_faces or not right_faces:
        return False
    return abs(left_faces - right_faces) / max(left_faces, right_faces) <= 0.05
