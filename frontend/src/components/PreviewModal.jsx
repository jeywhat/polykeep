import { useEffect, useState } from "react";
import ModelViewer from "./ModelViewer.jsx";
import { api } from "../api/client.js";
import { formatSize, humanize_name, statusLabel } from "../utils.js";

// Formats that can be previewed in the 3D viewer
const VIEWABLE_3D = ["stl", "obj", "ply", "gltf", "glb", "dae", "fbx", "3mf"];
// Formats that can have extracted thumbnails (LYS)
const THUMBNAIL_FORMATS = ["lys"];

export default function PreviewModal({ file, onClose, onMutate, notify }) {
  const [moveTarget, setMoveTarget] = useState("");
  const [modelInfo, setModelInfo] = useState(null);
  const [opening, setOpening] = useState(false);
  const isViewable3D = VIEWABLE_3D.includes(file.ext);
  const hasThumbnail = THUMBNAIL_FORMATS.includes(file.ext) && file.preview_url;
  const displayName = file.display_name || humanize_name(file.name, file.tags, file.ext);
  const modelVersion = `${file.scanned_at || ""}:${file.size || 0}:${file.hash || ""}`;

  function closeModal() {
    onClose?.(file.id);
  }

  useEffect(() => { setModelInfo(null); }, [file.id, modelVersion, file.ext]);

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
    if (!confirm(`Mettre à la corbeille « ${displayName} » ? (récupérable)`)) return;
    try {
      const updated = await api.deleteFile(file.id);
      notify("Fichier mis à la corbeille.", "success");
      onMutate(updated);
      closeModal();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function handleOpen() {
    if (["deleted", "missing"].includes(file.status)) return;
    setOpening(true);
    try {
      const info = await api.openInStudio(file.id);
      if (!info.open_path) {
        notify("Aucun chemin d'ouverture configuré (T3D_OPEN_MODE/T3D_SMB_ROOT).", "info");
        return;
      }
      localStorage.setItem("polykeep-helper-hint-seen", "1");
      notify("Si rien ne s'ouvre, lancez install-helper.ps1 sur votre PC.", "info");
      window.location.href = `polykeep://open?id=${file.id}&host=${encodeURIComponent(window.location.origin)}`;
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setOpening(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={closeModal}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 title={file.name}>{displayName}</h2>
          <button onClick={closeModal}>✕ Fermer</button>
        </div>
        <div className="modal-body">
          <div className="viewer">
            {isViewable3D ? (
              <ModelViewer
                key={`${file.id}:${modelVersion}:${file.ext}`}
                url={api.modelUrl(file.id, modelVersion)}
                onLoaded={setModelInfo}
                format={file.ext}
              />
            ) : hasThumbnail ? (
              <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <img src={file.preview_url} alt={displayName} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
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
              <div className="info-label">Nom du fichier</div>
              <div className="info-value">{file.name}</div>
            </div>
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
                  {Math.round(modelInfo.faces ?? modelInfo.triangles).toLocaleString("fr-FR")} faces
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

            <button
              className="primary"
              style={{ width: "100%", marginTop: 14 }}
              onClick={handleOpen}
              disabled={opening || ["deleted", "missing"].includes(file.status)}
            >
              {opening ? "Ouverture…" : "↗ Ouvrir dans Bambu Studio"}
            </button>

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
