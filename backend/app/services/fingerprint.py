"""Small, deterministic geometry fingerprints for cross-format matching."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


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
        if mesh is None:
            return None
        try:
            return _fingerprint_from_mesh(mesh)
        finally:
            del mesh
    except (OSError, ValueError, ImportError, TypeError):
        return None


def compute_fingerprint_mesh(mesh) -> str | None:
    """Compute the fingerprint from an already-loaded mesh (no extra load)."""
    try:
        return _fingerprint_from_mesh(mesh)
    except (OSError, ValueError, ImportError, TypeError):
        return None


def _count_components(face_adjacency: np.ndarray, total_faces: int) -> int:
    """Count connected face components with union-find (no scipy/networkx).

    Every face is a node of the graph; ``face_adjacency[:, :2]`` lists the
    face pairs sharing an edge. Isolated faces keep their own component, so
    the result matches ``mesh.split(only_watertight=False)`` without ever
    materializing copies of the geometry.
    """
    if total_faces <= 0:
        return 0
    parent = list(range(total_faces))
    count = total_faces

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    if face_adjacency is not None and face_adjacency.size:
        for a, b in face_adjacency[:, :2].tolist():
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
                count -= 1
    return count


def _fingerprint_from_mesh(mesh) -> str | None:
    if mesh is None or len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        return None
    extents = mesh.bounds[1] - mesh.bounds[0]
    scale = float(extents.max())
    if scale <= 0:
        return None
    components = _count_components(mesh.face_adjacency, len(mesh.faces))
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
