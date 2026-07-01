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

export default function FolderTree({ folders, current, onSelect }) {
  const tree = buildFolderTree(folders);
  const [expanded, setExpanded] = useState(loadExpanded);

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

  return (
    <nav className="folder-tree">
      <button
        className={`ft-item root ${current === "" ? "active" : ""}`}
        onClick={() => onSelect("")}
      >
        <span className="ft-icon">▸</span>
        <span className="ft-label">Tout</span>
        <span className="ft-count">{tree.totalCount}</span>
      </button>
      {children.map((node) => (
        <FolderNode
          key={node.path}
          node={node}
          depth={1}
          current={current}
          expanded={expanded}
          onToggle={toggle}
          onSelect={onSelect}
        />
      ))}
    </nav>
  );
}

function FolderNode({ node, depth, current, expanded, onToggle, onSelect }) {
  const isOpen = expanded.has(node.path);
  const isActive = current === node.path;
  const hasChildren = Object.keys(node.children).length > 0;
  const kids = hasChildren ? Object.values(node.children).sort(byName) : [];

  return (
    <div className="ft-node">
      <div
        className={`ft-item ${isActive ? "active" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
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
              onToggle={onToggle}
              onSelect={onSelect}
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
