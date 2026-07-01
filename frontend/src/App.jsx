import { useState, useEffect, useCallback } from "react";
import { api } from "./api/client.js";
import Toolbar from "./components/Toolbar.jsx";
import FileGrid from "./components/FileGrid.jsx";
import PreviewModal from "./components/PreviewModal.jsx";
import SortPanel from "./components/SortPanel.jsx";

export default function App() {
  const [files, setFiles] = useState([]);
  const [total, setTotal] = useState(0);
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);

  // Filters
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [ext, setExt] = useState("");
  const [activeTag, setActiveTag] = useState("");

  // UI state
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const notify = useCallback((message, kind = "info") => {
    setToast({ message, kind });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadFiles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listFiles({ q: query, status, ext, tag: activeTag });
      setFiles(data.items);
      setTotal(data.total);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }, [query, status, ext, activeTag, notify]);

  const loadTags = useCallback(async () => {
    try {
      setTags(await api.listTags());
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  useEffect(() => {
    loadTags();
  }, [loadTags, refreshKey]);

  // Debounce the search box.
  useEffect(() => {
    const t = setTimeout(loadFiles, 250);
    return () => clearTimeout(t);
  }, [query]);

  async function handleScan() {
    setScanning(true);
    try {
      const res = await api.scan();
      notify(
        `Scan terminé : ${res.scanned} fichiers, ${res.added} nouveaux, ` +
        `${res.missing} manquants.`,
        "success"
      );
      setRefreshKey((k) => k + 1);
      await loadFiles();
      await loadTags();
    } catch (e) {
      notify(e.message, "error");
    } finally {
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
  }

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">⬢ 3D File Sorter</span>
        <span className="spacer" />
        <span className="count">{total} fichiers indexés</span>
      </div>

      <div className="main">
        <div className="content">
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
          />
          <FileGrid files={files} onSelect={setSelected} loading={loading} />
        </div>

        <div className="sidebar">
          <SortPanel
            notify={notify}
            onChanged={() => {
              setRefreshKey((k) => k + 1);
              loadFiles();
              loadTags();
            }}
            refreshKey={refreshKey}
          />
        </div>
      </div>

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
