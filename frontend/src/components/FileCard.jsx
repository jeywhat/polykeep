import { formatSize, statusLabel, relativeDirLabel } from "../utils.js";
import { api } from "../api/client.js";
import { useRef, useState } from "react";

// Extension-specific colors for badges
const EXT_COLORS = {
  stl: "var(--stl)",
  lys: "var(--lys)",
  obj: "var(--obj, #e67e22)",
  ply: "var(--ply, #2ecc71)",
  "3mf": "var(--3mf, #9b59b6)",
  gltf: "var(--gltf, #3498db)",
  glb: "var(--glb, #2980b9)",
  fbx: "var(--fbx, #e74c3c)",
  dae: "var(--dae, #1abc9c)",
  amf: "var(--amf, #f39c12)",
};

export default function FileCard({ file, folder, onClick, onDragStart, onDragEnd }) {
  const extColor = EXT_COLORS[file.ext] || "var(--stl)";
  const relDir = relativeDirLabel(file.parent_dir, folder);
  const [dragging, setDragging] = useState(false);
  const suppressClick = useRef(false);
  const canDrag = !["deleted", "missing"].includes(file.status);

  function handleDragStart(e) {
    if (!canDrag) {
      e.preventDefault();
      return;
    }
    suppressClick.current = true;
    setDragging(true);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("application/x-polykeep-file", JSON.stringify(file));
    e.dataTransfer.setData("text/plain", String(file.id));
    onDragStart?.(file);
  }

  function handleDragEnd() {
    setDragging(false);
    onDragEnd?.();
    setTimeout(() => {
      suppressClick.current = false;
    }, 0);
  }

  function handleClick() {
    if (suppressClick.current) return;
    onClick(file);
  }

  return (
    <div
      className={`card ${dragging ? "dragging" : ""}`}
      draggable={canDrag}
      onClick={handleClick}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      title={canDrag ? "Glisser vers un dossier" : undefined}
    >
      <div className="thumb">
        {file.preview_url ? (
          <img src={api.thumbUrl(file.id)} alt={file.name} />
        ) : (
          <span className="ext-badge" style={{ color: extColor }}>
            {file.ext.toUpperCase()}
          </span>
        )}
      </div>
      <div className="name" title={file.name}>
        {file.name}
      </div>
      {relDir && (
        <div className="card-dir" title={file.parent_dir}>
          {relDir}
        </div>
      )}
      <div className="meta">
        <span>
          <span className={`status-dot status-${file.status}`} />
          {statusLabel(file.status)}
        </span>
        <span>{formatSize(file.size)}</span>
      </div>
      {file.tags?.length > 0 && (
        <div className="tags">
          {file.tags.slice(0, 4).map((t) => (
            <span key={t} className="badge">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
