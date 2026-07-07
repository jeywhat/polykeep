import { useState } from "react";
import ModelViewer from "./ModelViewer.jsx";
import { api } from "../api/client.js";
import { formatSize, statusLabel } from "../utils.js";

// Formats that can be previewed in the 3D viewer
const VIEWABLE_3D = ["stl", "obj", "ply", "gltf", "glb", "dae", "fbx", "3mf"];
// Formats that can have extracted thumbnails (LYS)
const THUMBNAIL_FORMATS = ["lys"];

export default function PreviewModal({ file, onClose, onMutate, notify }) {
  const [moveTarget, setMoveTarget] = useState("");
  const [modelInfo, setModelInfo] = useState(null);
  const isViewable3D = VIEWABLE_3D.includes(file.ext);
  const hasThumbnail = THUMBNAIL_FORMATS.includes(file.ext) && file.preview_url;

  if (!file) return null;

  async function handleMove() {
    if (!moveTarget.trim()) {
      notify("Indiquez un dossier de destination.", "error");
      return;
    }
    try {
      const updated = await api.moveFile(file.id, moveTarget.trim());
      notify(`Déplacé vers « ${moveTarget.trim()} »`, "success");
      onMutate(updated);
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function handleDelete() {
    if (!confirm(`Mettre à la corbeille « ${file.name} » ? (récupérable)`)) return;
    try {
      const updated = await api.deleteFile(file.id);
      notify("Fichier mis à la corbeille.", "success");
      onMutate(updated);
      onClose();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 title={file.name}>{file.name}</h2>
          <button onClick={onClose}>✕ Fermer</button>
        </div>
        <div className="modal-body">
          <div className="viewer">
            {isViewable3D ? (
              <ModelViewer url={api.modelUrl(file.id)} onLoaded={setModelInfo} format={file.ext} />
            ) : hasThumbnail ? (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <img
                  src={api.thumbUrl(file.id)}
                  alt={file.name}
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
              </div>
            ) : (
              <div className="empty">
                <h2>Pas d'aperçu 3D</h2>
                <p>
                  Ce format ({file.ext.toUpperCase()}) n'est pas encore supporté pour la
                  prévisualisation 3D interactive.
                </p>
              </div>
            )}
          </div>
          <div className="viewer-info">
            <div className="info-row">
              <div className="info-label">Format</div>
              <div className="info-value">
                <span className={`badge ${file.ext}`}>{file.ext.toUpperCase()}</span>
              </div>
            </div>
            <div className="info-row">
              <div className="info-label">Statut</div>
              <div className="info-value">
                <span className={`status-dot status-${file.status}`} />
                {statusLabel(file.status)}
              </div>
            </div>
            <div className="info-row">
              <div className="info-label">Taille</div>
              <div className="info-value">{formatSize(file.size)}</div>
            </div>
            {modelInfo && (
              <div className="info-row">
                <div className="info-label">Géométrie</div>
                <div className="info-value">
                  {Math.round(modelInfo.triangles).toLocaleString("fr-FR")} triangles
                </div>
              </div>
            )}
            <div className="info-row">
              <div className="info-label">Dossier</div>
              <div className="info-value">{file.parent_dir || "/"}</div>
            </div>
            {file.hash && (
              <div className="info-row">
                <div className="info-label">Hash (SHA-256)</div>
                <div className="info-value" style={{ fontFamily: "monospace", fontSize: 11 }}>
                  {file.hash.slice(0, 16)}…
                </div>
              </div>
            )}
            {file.tags?.length > 0 && (
              <div className="info-row">
                <div className="info-label">Tags</div>
                <div className="info-value" style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {file.tags.map((t) => (
                    <span key={t} className="badge">{t}</span>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
              <div className="info-label" style={{ marginBottom: 6 }}>Déplacer vers</div>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  type="text"
                  placeholder="ex: Trié/Guerre"
                  value={moveTarget}
                  onChange={(e) => setMoveTarget(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button className="success" onClick={handleMove}>Déplacer</button>
              </div>
              <button className="danger" style={{ width: "100%", marginTop: 10 }} onClick={handleDelete}>
                🗑 Mettre à la corbeille
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
