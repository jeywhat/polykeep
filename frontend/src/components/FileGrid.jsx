import FileCard from "./FileCard.jsx";
import { groupBySubfolder } from "../utils.js";
import { useState } from "react";

export default function FileGrid({
  files,
  folder,
  onSelect,
  draggingFile,
  onDragStart,
  onDragEnd,
  onDropFile,
  loading,
}) {
  const [dropTarget, setDropTarget] = useState(null);

  if (loading) return <div className="loading">Chargement…</div>;
  if (!files?.length)
    return (
      <div className="empty">
        <h2>Aucun fichier</h2>
        <p>Aucun fichier dans ce dossier (ou lancez un scan pour indexer).</p>
      </div>
    );

  const groups = groupBySubfolder(files, folder);

  function folderPathForGroup(label) {
    return folder ? `${folder}/${label}` : label;
  }

  function allowFolderDrop(e, targetPath) {
    if (!draggingFile) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "move";
    setDropTarget(targetPath);
  }

  function handleFolderDrop(e, targetPath) {
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(null);
    const file = readDraggedFile(e, draggingFile);
    if (file) onDropFile?.(file, targetPath);
  }

  function handleFolderDragLeave(e) {
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setDropTarget(null);
  }

  return (
    <div className="groups">
      {groups.map((g) => {
        const targetPath = g.kind === "folder" ? folderPathForGroup(g.label) : "";
        return g.kind === "root" ? (
          <section key={g.key} className="file-group">
            {g.label && (
              <h3 className="group-header">
                <span className="group-icon">📄</span>
                <span>Dans ce dossier</span>
                <span className="group-count">{g.files.length}</span>
              </h3>
            )}
            <div className="grid">
              {g.files.map((f) => (
                <FileCard
                  key={f.id}
                  file={f}
                  folder={folder}
                  onClick={onSelect}
                  onDragStart={onDragStart}
                  onDragEnd={onDragEnd}
                />
              ))}
            </div>
          </section>
        ) : (
          <section
            key={g.key}
            className={`file-group folder-drop-zone ${draggingFile ? "can-drop" : ""} ${
              dropTarget === targetPath ? "drop-target" : ""
            }`}
            title={`Déplacer vers ${targetPath}`}
            onDragOver={(e) => allowFolderDrop(e, targetPath)}
            onDragLeave={handleFolderDragLeave}
            onDrop={(e) => handleFolderDrop(e, targetPath)}
          >
            <h3
              className="group-header"
            >
              <span className="group-icon">📁</span>
              <span className="group-name">{g.label}</span>
              <span className="group-count">{g.files.length}</span>
            </h3>
            <div className="grid">
              {g.files.map((f) => (
                <FileCard
                  key={f.id}
                  file={f}
                  folder={folder}
                  onClick={onSelect}
                  onDragStart={onDragStart}
                  onDragEnd={onDragEnd}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function readDraggedFile(e, fallback) {
  const payload = e.dataTransfer.getData("application/x-polykeep-file");
  if (!payload) return fallback;
  try {
    return JSON.parse(payload);
  } catch {
    return fallback;
  }
}
