import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "./api/client.js";
import Toolbar from "./components/Toolbar.jsx";
import FileGrid from "./components/FileGrid.jsx";
import PreviewModal from "./components/PreviewModal.jsx";
import SortPanel from "./components/SortPanel.jsx";
import FolderTree from "./components/FolderTree.jsx";
import Breadcrumb from "./components/Breadcrumb.jsx";
import ImportPanel from "./components/ImportPanel.jsx";

const ACTIVE_SCAN_PHASES = new Set([
  "discovery",
  "db_upsert",
  "missing_mark",
  "thumbnails",
  "apply_results",
  "suggestions",
]);

export default function App() {
  const [files, setFiles] = useState([]);
  const [total, setTotal] = useState(0);
  const [tags, setTags] = useState([]);
  const [folders, setFolders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(null);
  const scanOwner = useRef(false);

  // Filters
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [ext, setExt] = useState("");
  const [activeTag, setActiveTag] = useState("");
  const [folder, setFolder] = useState(""); // "" = root (everything)

  // UI state
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [draggingFile, setDraggingFile] = useState(null);
  const [view, setView] = useState("library");

  const notify = useCallback((message, kind = "info") => {
    setToast({ message, kind });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      // Load the whole folder (recursively) — page_size is bumped server-side.
      const data = await api.listFiles({
        q: query,
        status,
        ext,
        tag: activeTag,
        folder,
        page_size: 5000,
      });
      setFiles(data.items);
      setTotal(data.total);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [query, status, ext, activeTag, folder, notify]);

  const loadTags = useCallback(async () => {
    try {
      setTags(await api.listTags());
    } catch {
      /* non-critical */
    }
  }, []);

  const loadFolders = useCallback(async () => {
    try {
      setFolders(await api.listFolders());
    } catch {
      /* tree is non-critical */
    }
  }, []);

  // Poll scan progress while scanning
  useEffect(() => {
    if (!scanning) {
      setScanProgress(null);
      return;
    }
    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        try {
          const prog = await api.scanProgress();
          if (cancelled) return;
          setScanProgress(prog);
          if (!scanOwner.current && (prog.phase === "complete" || prog.phase === "error")) {
            setScanning(false);
            return;
          }
        } catch {
          /* ignore */
        }
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    poll();
    return () => { cancelled = true; };
  }, [scanning]);

  // Resume displaying a scan started in another tab before this page loaded.
  useEffect(() => {
    let cancelled = false;
    api.scanProgress().then((prog) => {
      if (!cancelled && !scanOwner.current && ACTIVE_SCAN_PHASES.has(prog.phase)) {
        setScanProgress(prog);
        setScanning(true);
      }
    }).catch(() => {
      /* no active scan or backend unavailable */
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    loadTags();
    loadFolders();
  }, [loadTags, loadFolders, refreshKey]);

  // Debounce the search box.
  useEffect(() => {
    const t = setTimeout(loadFiles, 250);
    return () => clearTimeout(t);
  }, [query]);

  async function handleScan() {
    scanOwner.current = true;
    setScanning(true);
    try {
      const res = await api.scan();
      const message =
        `Scan terminé : ${res.scanned} fichiers, ${res.added} nouveaux, ` +
        `${res.missing} manquants.`;
      notify(
        res.suggestions_error
          ? `${message} Suggestions non recalculées : ${res.suggestions_error}`
          : message,
        res.suggestions_error ? "error" : "success"
      );
      setRefreshKey((k) => k + 1);
      await loadFiles();
      await loadTags();
      await loadFolders();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      scanOwner.current = false;
      setScanning(false);
    }
  }

  function handleMutate(updated) {
    // Update the moved/deleted file in place and refresh derived data.
    setFiles((prev) =>
      prev.map((f) => (f.id === updated.id ? { ...f, ...updated } : f))
    );
    setRefreshKey((k) => k + 1);
    loadTags();
    loadFolders();
  }

  async function handleDropMove(file, targetDir) {
    if (!file) return;
    const normalizedTarget = normalizeFolderPath(targetDir);
    if (file.parent_dir === normalizedTarget) {
      notify("Ce fichier est déjà dans ce dossier.", "info");
      return;
    }
    try {
      const updated = await api.moveFile(file.id, normalizedTarget);
      notify(
        `« ${file.name} » déplacé vers ${normalizedTarget ? `« ${normalizedTarget} »` : "la racine"}.`,
        "success"
      );
      handleMutate(updated);
      await loadFiles();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function handleDropMoveToNewFolder(file, baseFolder = "") {
    if (!file) return;
    const base = normalizeFolderPath(baseFolder);
    const suffix = base ? `${base}/` : "";
    const input = prompt(
      "Nouveau dossier de destination",
      suffix
    );
    if (input === null) return;
    const targetDir = normalizeFolderPath(input);
    if (!targetDir) {
      notify("Indiquez un dossier de destination.", "error");
      return;
    }
    await handleDropMove(file, targetDir);
  }

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">⬢ PolyKeep</span>
         <span className="spacer" />
         <button onClick={() => setView(view === "library" ? "imports" : "library")}>
           {view === "library" ? "Importer" : "Bibliothèque"}
         </button>
         <span className="count">{total} fichiers indexés</span>
      </div>

      {view === "imports" ? <main className="import-content"><ImportPanel notify={notify} onImported={async () => {
        setRefreshKey((k) => k + 1);
        await loadFiles();
        await loadFolders();
      }} /></main> : <div className="main">
        <aside className="folder-rail">
          <div className="rail-header">Dossiers</div>
          <FolderTree
            folders={folders}
            current={folder}
            draggingFile={draggingFile}
            onSelect={setFolder}
            onDropFile={handleDropMove}
            onDropFileToNewFolder={handleDropMoveToNewFolder}
          />
        </aside>

        <div className="content">
          <Breadcrumb folder={folder} onNavigate={setFolder} />
          <Toolbar
            query={query}
            setQuery={setQuery}
            status={status}
            setStatus={setStatus}
            ext={ext}
            setExt={setExt}
            tags={tags}
            activeTag={activeTag}
            setActiveTag={setActiveTag}
            total={total}
            onScan={handleScan}
            scanning={scanning}
            scanProgress={scanProgress}
          />
          <FileGrid
            files={files}
            folder={folder}
            onSelect={setSelected}
            draggingFile={draggingFile}
            onDragStart={setDraggingFile}
            onDragEnd={() => setDraggingFile(null)}
            onDropFile={handleDropMove}
            loading={loading}
            notify={notify}
          />
        </div>

        <div className="sidebar">
          <SortPanel
            notify={notify}
            onChanged={() => {
              setRefreshKey((k) => k + 1);
              loadFiles();
              loadTags();
              loadFolders();
            }}
            refreshKey={refreshKey}
          />
        </div>
      </div>}

      {selected && (
        <PreviewModal
          file={selected}
          onClose={() => setSelected(null)}
          onMutate={(updated) => {
            handleMutate(updated);
            setSelected((s) => ({ ...s, ...updated }));
          }}
          notify={notify}
        />
      )}

      {toast && <div className={`toast ${toast.kind}`}>{toast.message}</div>}
    </div>
  );
}

function normalizeFolderPath(path) {
  return (path || "")
    .trim()
    .replaceAll("\\", "/")
    .replace(/\/+/g, "/")
    .replace(/^\/|\/$/g, "");
}
