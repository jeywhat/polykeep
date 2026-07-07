"""Render various 3D mesh formats to PNG thumbnails (CPU-only, headless).

Supports: STL, OBJ, PLY, GLTF, GLB, 3MF, DAE (Collada), FBX (via trimesh/assimp),
and potentially others supported by trimesh.

Framing strategy: render on transparent canvas, measure non-transparent footprint,
crop tight, scale to fill ratio, centre in square output — same as the STL renderer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

# Final thumbnail resolution (square).
_IMG_SIZE = 256
# Render at 2x then downscale for crisper edges / anti-aliasing.
_RENDER_SCALE = 2
# Target fill ratio of the object within the final frame (0-1).
_FILL = 0.9
# Isometric-ish viewing angle.
_ELEV, _AZIM = 20.0, 45.0


def _load_mesh(path: Path) -> Optional["trimesh.Trimesh"]:
    """Load a mesh file via trimesh. Returns None on failure."""
    try:
        import trimesh
    except ImportError:
        return None

    try:
        mesh = trimesh.load(str(path), force="mesh")
        if isinstance(mesh, trimesh.Scene):
            # Merge all geometries in the scene into a single mesh.
            mesh = mesh.dump().sum()
        if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
            return None
        return mesh
    except Exception:
        return None


def _prepare_vertices(mesh: "trimesh.Trimesh") -> np.ndarray:
    """Centre + normalise mesh so longest bbox side = 1. Returns (N, 3) vertices."""
    vertices = mesh.vertices.copy()
    min_corner = vertices.min(axis=0)
    max_corner = vertices.max(axis=0)
    center = (min_corner + max_corner) / 2
    longest = float((max_corner - min_corner).max())
    if longest <= 0:
        return np.zeros((0, 3), dtype=np.float32)
    vertices = (vertices - center) / longest
    return vertices.astype(np.float32)


def _face_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Per-face unit normals for (F, 3, 3) vertex array."""
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    n = np.cross(v1 - v0, v2 - v0)
    norms = np.linalg.norm(n, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (n / norms).astype(np.float32)


def _render_mesh(vertices: np.ndarray, faces: np.ndarray, out_path: Path) -> bool:
    """Render mesh to PNG using matplotlib Agg backend."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    if len(vertices) == 0 or len(faces) == 0:
        return False

    normals = _face_normals(vertices, faces)
    light = np.array([0.3, 0.3, 1.0], dtype=np.float32)
    light = light / np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(normals @ light, 0.0, 1.0)
    accent = np.array([1.0, 0.549, 0.165], dtype=np.float32)  # #ff8c2a
    face_colors = np.clip(accent * shade[:, None], 0.0, 1.0)

    canvas_px = _IMG_SIZE * _RENDER_SCALE
    fig = plt.figure(figsize=(canvas_px / 100, canvas_px / 100), dpi=100)
    try:
        ax = fig.add_subplot(111, projection="3d")
        coll = Poly3DCollection(
            vertices[faces], facecolors=face_colors, edgecolors="none", linewidths=0
        )
        ax.add_collection3d(coll)
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(-0.5, 0.5)
        ax.set_zlim(-0.5, 0.5)
        ax.view_init(elev=_ELEV, azim=_AZIM)
        ax.set_box_aspect((1, 1, 1))
        ax.set_axis_off()
        ax.margins(0)
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        framed = _frame_pixels(rgba, _IMG_SIZE, _FILL)
    finally:
        plt.close(fig)

    return _write_png(framed, out_path)


def _frame_pixels(rgba: np.ndarray, out_size: int, fill: float) -> np.ndarray:
    """Crop to alpha bbox, pad to square, scale to fill ratio, centre."""
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if len(xs) == 0:
        return np.zeros((out_size, out_size, 4), dtype=np.uint8)

    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    crop = rgba[y0:y1, x0:x1]

    h, w = crop.shape[:2]
    side = max(h, w)
    padded = np.zeros((side, side, 4), dtype=np.uint8)
    off_y = (side - h) // 2
    off_x = (side - w) // 2
    padded[off_y : off_y + h, off_x : off_x + w] = crop

    target = int(round(out_size * fill))
    scaled = _resize_nearest(padded, target, target)

    out = np.zeros((out_size, out_size, 4), dtype=np.uint8)
    off_y = (out_size - target) // 2
    off_x = (out_size - target) // 2
    out[off_y : off_y + target, off_x : off_x + target] = scaled
    return out


def _resize_nearest(src: np.ndarray, new_h: int, new_w: int) -> np.ndarray:
    """Nearest-neighbour resize (H, W, 4) uint8."""
    h, w = src.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((new_h, new_w, 4), dtype=np.uint8)
    row_idx = (np.arange(new_h) * h // new_h).clip(0, h - 1)
    col_idx = (np.arange(new_w) * w // new_w).clip(0, w - 1)
    return src[row_idx[:, None], col_idx[None, :]]


def _write_png(rgba: np.ndarray, out_path: Path) -> bool:
    """Write (H, W, 4) uint8 array to PNG via matplotlib."""
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(rgba.shape[1] / 100, rgba.shape[0] / 100), dpi=100)
    try:
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(rgba, interpolation="bilinear")
        ax.set_axis_off()
        fig.savefig(
            str(out_path),
            transparent=True,
            bbox_inches="tight",
            pad_inches=0,
        )
    finally:
        plt.close(fig)
    return out_path.is_file()


# Public API ---------------------------------------------------------------

def render_mesh(path: Path, out_path: Path) -> bool:
    """Render any trimesh-supported mesh to a centred PNG thumbnail."""
    mesh = _load_mesh(path)
    if mesh is None:
        return False
    vertices = _prepare_vertices(mesh)
    if len(vertices) == 0:
        return False
    faces = mesh.faces
    return _render_mesh(vertices, faces, out_path)


def can_render(ext: str) -> bool:
    """Return True if this renderer can handle the given extension."""
    return ext.lower() in {
        ".stl",
        ".obj",
        ".ply",
        ".gltf",
        ".glb",
        ".3mf",
        ".dae",
        ".fbx",
        ".x3d",
        ".off",
        ".stp",
        ".step",
    }