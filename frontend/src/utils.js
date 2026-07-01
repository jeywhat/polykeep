// Small shared helpers.

export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "—";
  const units = ["o", "Ko", "Mo", "Go"];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function statusLabel(status) {
  const map = {
    unsorted: "À trier",
    sorted: "Trié",
    archived: "Archivé",
    deleted: "Corbeille",
    missing: "Manquant",
  };
  return map[status] || status;
}

// ---------- Folder helpers ----------
// parent_dir is POSIX-style relative to /storage, "" meaning root.

/**
 * Split a POSIX folder path into clean segments, dropping empties.
 * "" → [], "A" → ["A"], "A/B/C" → ["A","B","C"].
 */
function folderSegments(folder) {
  return (folder || "").split("/").filter(Boolean);
}

/**
 * Build a nested folder tree from the flat { path, count } list returned by
 * /api/folders. Each node carries:
 *   - name      : last path segment ("Voron")
 *   - path      : full path ("Imprimantes/Voron")
 *   - count     : files directly in this folder (from the API)
 *   - children  : { name -> node }
 * An artificial root node (path "") holds top-level folders.
 *
 * NOTE: a folder may appear in the tree even with count 0 when it only exists
 * as a parent of deeper folders (we synthesise it). `totalCount` aggregates
 * the node's own files + everything beneath it, for display.
 */
export function buildFolderTree(folders) {
  const root = { name: "", path: "", count: 0, totalCount: 0, children: {} };

  for (const { path, count } of folders) {
    const segs = folderSegments(path);
    let node = root;
    for (let i = 0; i < segs.length; i++) {
      const seg = segs[i];
      const nodePath = segs.slice(0, i + 1).join("/");
      node.children[seg] ??= {
        name: seg,
        path: nodePath,
        count: 0,
        totalCount: 0,
        children: {},
      };
      node = node.children[seg];
    }
    node.count += count || 0;
  }

  // Bottom-up aggregation of totalCount.
  function aggregate(node) {
    let total = node.count;
    for (const child of Object.values(node.children)) {
      total += aggregate(child);
    }
    node.totalCount = total;
    return total;
  }
  aggregate(root);
  return root;
}

/**
 * Group files by the subfolder directly under `folder` (recursive view).
 * Returns an ordered array of groups:
 *   [{ key, label, kind: "folder"|"root", files: [...] }]
 * Files directly in `folder` form a "root" group (kind "root").
 * Files deeper down are grouped under their first segment below `folder`,
 * with the group label being that segment.
 */
export function groupBySubfolder(files, folder = "") {
  const prefixLen = folderSegments(folder).length;
  const groups = new Map(); // key -> { key, label, kind, files }

  for (const f of files) {
    const segs = folderSegments(f.parent_dir);
    if (segs.length <= prefixLen) {
      // Directly in the current folder (or above, e.g. root-level file).
      const key = "\u0000root";
      if (!groups.has(key))
        groups.set(key, { key, label: null, kind: "root", files: [] });
      groups.get(key).files.push(f);
    } else {
      const seg = segs[prefixLen];
      const key = seg;
      if (!groups.has(key))
        groups.set(key, { key, label: seg, kind: "folder", files: [] });
      groups.get(key).files.push(f);
    }
  }

  // Folders first (alphabetical), then root files last.
  const arr = [...groups.values()];
  arr.sort((a, b) => {
    if (a.kind === "folder" && b.kind === "root") return -1;
    if (a.kind === "root" && b.kind === "folder") return 1;
    return (a.label || "").localeCompare(b.label || "", "fr", { sensitivity: "base" });
  });
  return arr;
}

/**
 * Breadcrumb segments for a folder path.
 * [{ label: "Accueil", folder: "" }, { label: "A", folder: "A" }, ...]
 */
export function breadcrumbSegments(folder) {
  const segs = folderSegments(folder);
  const crumbs = [{ label: "Accueil", folder: "" }];
  let acc = "";
  for (const s of segs) {
    acc = acc ? `${acc}/${s}` : s;
    crumbs.push({ label: s, folder: acc });
  }
  return crumbs;
}

/**
 * Short relative path of a file under `folder`, for compact display.
 * "Imprimantes/Voron/Crêtes/x.stl" under "Imprimantes" → "…/Voron/Crêtes"
 * Returns "" when the file is directly inside `folder`.
 */
export function relativeDirLabel(parentDir, folder = "") {
  const parentSegs = folderSegments(parentDir);
  const folderSegs = folderSegments(folder);
  if (parentSegs.length <= folderSegs.length) return "";
  const rel = parentSegs.slice(folderSegs.length).join("/");
  // Prefix with ellipsis when the relative path is nested, to hint depth.
  return rel;
}
