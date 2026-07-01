"""Render an STL file to a centred PNG thumbnail (CPU-only, headless).

The container has no GPU, so we can't rely on Three.js / OpenGL server-side.
Instead we parse the mesh with ``numpy-stl`` and rasterise it with the
matplotlib Agg backend, which is pure software and works everywhere.

Framing is the tricky part and a naive bounding-box fit produces empty
thumbnails for models that are flat along the view axis (a coin on its edge, a
wall seen from the front, …). Rather than try to match matplotlib's internal
3-D projection math, we **frame on pixels**: render the mesh on a transparent
canvas, measure the actual non-transparent footprint, then crop tight and
place it centred in the final square at a fixed fill ratio. This guarantees a
filled frame and a centred object regardless of the camera projection.

``render_stl`` never raises: a corrupt or unparseable STL returns ``False`` and
the rest of the scan keeps running (same contract as the .lys thumbnail code).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Final thumbnail resolution (square).
_IMG_SIZE = 256
# Render at 2x then downscale for crisper edges / anti-aliasing.
_RENDER_SCALE = 2
# Target fill ratio of the object within the final frame (0-1). High enough to
# avoid empty scenes, low enough to never clip.
_FILL = 0.9
# Isometric-ish viewing angle.
_ELEV, _AZIM = 20.0, 45.0


def _load_mesh(path: Path) -> np.ndarray | None:
    """Load an STL and return an (N, 3) vertex array, or ``None``."""
    try:
        from stl import mesh as stl_mesh
    except ImportError:  # pragma: no cover - dependency declared in requirements
        return None

    try:
        m = stl_mesh.Mesh.from_file(str(path))
    except Exception:  # noqa: BLE001 - numpy-stl raises various errors
        return None
    if len(m.vectors) == 0:
        return None
    return m.vectors.reshape(-1, 3)


def render_stl(path: Path, out_path: Path) -> bool:
    """Render ``path`` to ``out_path`` (PNG). Returns ``True`` on success."""
    vertices = _load_mesh(path)
    if vertices is None:
        return False
    try:
        return _render(vertices, out_path)
    except Exception:  # noqa: BLE001 - never let rendering kill the scan
        return False


def _render(vertices: np.ndarray, out_path: Path) -> bool:
    import matplotlib

    matplotlib.use("Agg")  # headless, no display required
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    # --- 1. Centre + normalise so the longest bbox side has length 1. -------
    min_corner = vertices.min(axis=0)
    max_corner = vertices.max(axis=0)
    center = (min_corner + max_corner) / 2
    longest = float((max_corner - min_corner).max())
    if longest <= 0:
        return False
    vertices = (vertices - center) / longest  # in [-0.5, 0.5]

    n_faces = len(vertices) // 3
    polys = vertices.reshape(n_faces, 3, 3)

    # --- 2. Per-face shading (ambient + diffuse) for a 3-D look. ------------
    normals = _face_normals(polys)
    light = np.array([0.3, 0.3, 1.0])
    light = light / np.linalg.norm(light)
    shade = 0.35 + 0.65 * np.clip(normals @ light, 0.0, 1.0)
    accent = np.array([1.0, 0.549, 0.165])  # #ff8c2a
    face_colors = np.clip(accent[None, :] * shade[:, None], 0.0, 1.0)

    canvas_px = _IMG_SIZE * _RENDER_SCALE
    fig = plt.figure(figsize=(canvas_px / 100, canvas_px / 100), dpi=100)
    try:
        ax = fig.add_subplot(111, projection="3d")
        coll = Poly3DCollection(
            polys, facecolors=face_colors, edgecolors="none", linewidths=0
        )
        ax.add_collection3d(coll)
        # Fit the axis box to the mesh bounds (tight).
        ax.set_xlim(-0.5, 0.5)
        ax.set_ylim(-0.5, 0.5)
        ax.set_zlim(-0.5, 0.5)
        ax.view_init(elev=_ELEV, azim=_AZIM)
        ax.set_box_aspect((1, 1, 1))
        ax.set_axis_off()
        ax.margins(0)
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        # --- 3. Grab pixels and frame on the alpha channel. -----------------
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        final = _frame_pixels(rgba, _IMG_SIZE, _FILL)
    finally:
        plt.close(fig)

    # --- 4. Write the framed PNG (transparent background). ------------------
    return _write_png(final, out_path)


def _frame_pixels(rgba: np.ndarray, out_size: int, fill: float) -> np.ndarray:
    """Crop to the object's alpha bbox and centre it in a square at ``fill``.

    ``rgba`` is an (H, W, 4) uint8 array. Returns an (out_size, out_size, 4)
    array with the object centred and scaled to occupy ``fill`` of the frame.
    """
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > 0)
    if len(xs) == 0:
        # Nothing drawn — return a transparent square.
        return np.zeros((out_size, out_size, 4), dtype=np.uint8)

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    crop = rgba[y0:y1, x0:x1]

    # Pad the crop to a square centred on the object so aspect ratio is kept.
    h, w = crop.shape[:2]
    side = max(h, w)
    padded = np.zeros((side, side, 4), dtype=np.uint8)
    off_y = (side - h) // 2
    off_x = (side - w) // 2
    padded[off_y : off_y + h, off_x : off_x + w] = crop

    # Scale the object square to ``fill`` of the output, then centre.
    target = int(round(out_size * fill))
    scaled = _resize_nearest(padded, target, target)

    out = np.zeros((out_size, out_size, 4), dtype=np.uint8)
    off_y = (out_size - target) // 2
    off_x = (out_size - target) // 2
    out[off_y : off_y + target, off_x : off_x + target] = scaled
    return out


def _resize_nearest(src: np.ndarray, new_h: int, new_w: int) -> np.ndarray:
    """Nearest-neighbour resize of an (H, W, 4) uint8 array. No PIL needed."""
    h, w = src.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((new_h, new_w, 4), dtype=np.uint8)
    row_idx = (np.arange(new_h) * h // new_h).clip(0, h - 1)
    col_idx = (np.arange(new_w) * w // new_w).clip(0, w - 1)
    return src[row_idx[:, None], col_idx[None, :]]


def _write_png(rgba: np.ndarray, out_path: Path) -> bool:
    """Write an (H, W, 4) uint8 array to a PNG using matplotlib's Agg writer."""
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


def _face_normals(polys: np.ndarray) -> np.ndarray:
    """Per-face unit normals for an (F, 3, 3) array."""
    v0 = polys[:, 0]
    v1 = polys[:, 1]
    v2 = polys[:, 2]
    n = np.cross(v1 - v0, v2 - v0)
    norm = np.linalg.norm(n, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return n / norm
