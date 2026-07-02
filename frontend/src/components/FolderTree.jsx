import { useEffect, useState } from "react";
import { buildFolderTree } from "../utils.js";

const STORAGE_KEY = "polykeep:expandedFolders";

function loadExpanded() {
  try {
    return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function persistExpanded(set) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    /* storage may be unavailable */
  }
}

export default function FolderTree({
  folders,
  current,
  draggingFile,
  onSelect,
  onDropFile,
  onDropFileToNewFolder,
}) {
  const tree = buildFolderTree(folders);
  const [expanded, setExpanded] = useState(loadExpanded);
  const [dropTarget, setDropTarget] = useState(null);

  // Reload from storage on mount (in case it changed in another tab).
  useEffect(() => {
    setExpanded(loadExpanded());
  }, []);

  function toggle(path) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      persistExpanded(next);
      return next;
    });
  }

  // Auto-expand the ancestors of the current folder so it stays visible.
  useEffect(() => {
    if (!current) return;
    const segs = current.split("/").filter(Boolean);
    let acc = "";
    const toExpand = [];
    for (const s of segs) {
      acc = acc ? `${acc}/${s}` : s;
      toExpand.push(acc);
    }
    setExpanded((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const p of toExpand) {
        if (!next.has(p)) {
          next.add(p);
          changed = true;
        }
      }
      if (changed) persistExpanded(next);
      return changed ? next : prev;
    });
  }, [current]);

  const children = Object.values(tree.children).sort(byName);

  function handleDrop(e, targetPath) {
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(null);
    const file = readDraggedFile(e, draggingFile);
    if (file) onDropFile?.(file, targetPath);
  }

  function handleNewFolderDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDropTarget(null);
    const file = readDraggedFile(e, draggingFile);
    if (file) onDropFileToNewFolder?.(file, current);
  }

  function allowDrop(e, targetPath) {
    if (!draggingFile) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDropTarget(targetPath);
  }

  return (
    <nav className="folder-tree">
      <button
        className={`ft-item root ${current === "" ? "active" : ""} ${dropTarget === "" ? "drop-target" : ""}`}
        onClick={() => onSelect("")}
        onDragOver={(e) => allowDrop(e, "")}
        onDragLeave={() => setDropTarget(null)}
        onDrop={(e) => handleDrop(e, "")}
      >
        <span className="ft-icon">▸</span>
        <span className="ft-label">Tout</span>
        <span className="ft-count">{tree.totalCount}</span>
      </button>
      {draggingFile && (
        <button
          className={`ft-new-folder ${dropTarget === "__new" ? "drop-target" : ""}`}
          onDragOver={(e) => allowDrop(e, "__new")}
          onDragLeave={() => setDropTarget(null)}
          onDrop={handleNewFolderDrop}
        >
          <span className="ft-icon">＋</span>
          <span className="ft-label">Nouveau dossier…</span>
        </button>
      )}
      {children.map((node) => (
        <FolderNode
          key={node.path}
          node={node}
          depth={1}
          current={current}
          expanded={expanded}
          dropTarget={dropTarget}
          draggingFile={draggingFile}
          onToggle={toggle}
          onSelect={onSelect}
          onDropFile={onDropFile}
          onDropTargetChange={setDropTarget}
        />
      ))}
    </nav>
  );
}

function FolderNode({
  node,
  depth,
  current,
  expanded,
  dropTarget,
  draggingFile,
  onToggle,
  onSelect,
  onDropFile,
  onDropTargetChange,
}) {
  const isOpen = expanded.has(node.path);
  const isActive = current === node.path;
  const hasChildren = Object.keys(node.children).length > 0;
  const kids = hasChildren ? Object.values(node.children).sort(byName) : [];

  function allowDrop(e) {
    if (!draggingFile) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "move";
    onDropTargetChange(node.path);
  }

  function handleDragEnter(e) {
    if (!draggingFile) return;
    e.stopPropagation();
    if (hasChildren && !isOpen) onToggle(node.path);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    onDropTargetChange(null);
    const file = readDraggedFile(e, draggingFile);
    if (file) onDropFile?.(file, node.path);
  }

  return (
    <div className="ft-node">
      <div
        className={`ft-item ${isActive ? "active" : ""} ${dropTarget === node.path ? "drop-target" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onDragEnter={handleDragEnter}
        onDragOver={allowDrop}
        onDragLeave={() => onDropTargetChange(null)}
        onDrop={handleDrop}
      >
        <button
          className="ft-twisty"
          onClick={() => hasChildren && onToggle(node.path)}
          tabIndex={hasChildren ? 0 : -1}
          aria-label={isOpen ? "Réduire" : "Déplier"}
        >
          {hasChildren ? (isOpen ? "▾" : "▸") : "•"}
        </button>
        <button className="ft-select" onClick={() => onSelect(node.path)} title={node.path}>
          <span className="ft-label">{node.name}</span>
        </button>
        <span className="ft-count">{node.totalCount}</span>
      </div>
      {isOpen && hasChildren && (
        <div className="ft-children">
          {kids.map((kid) => (
            <FolderNode
              key={kid.path}
              node={kid}
              depth={depth + 1}
              current={current}
              expanded={expanded}
              dropTarget={dropTarget}
              draggingFile={draggingFile}
              onToggle={onToggle}
              onSelect={onSelect}
              onDropFile={onDropFile}
              onDropTargetChange={onDropTargetChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function byName(a, b) {
  return a.name.localeCompare(b.name, "fr", { sensitivity: "base", numeric: true });
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
