import { useState, useEffect } from "react";
import { api } from "../api/client.js";

const TYPE_LABEL = {
  duplicate: "Doublon",
  group: "Regroupement",
  move: "Déplacement",
};

// Maps suggestion payloads to file names via a quick lookup of the current
// file list. Falls back to ids if names aren't available.
function useFileNameMap(refreshKey) {
  const [map, setMap] = useState({});
  useEffect(() => {
    let cancelled = false;
    // Load a big page so most names resolve for display in the panel.
    api.listFiles({ page: 1, page_size: 500 }).then((data) => {
      if (cancelled) return;
      const m = {};
      data.items.forEach((f) => (m[f.id] = f));
      setMap(m);
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);
  return map;
}

function SuggestionCard({ s, fileMap, onApply, onReject, busy }) {
  const ids = s.payload.file_ids || (s.payload.file_id ? [s.payload.file_id] : []);
  const files = ids.map((id) => fileMap[id]).filter(Boolean);

  return (
    <div className="suggestion">
      <div className="s-title">
        <span className={`type-pill ${s.type}`}>{TYPE_LABEL[s.type] || s.type}</span>
        {s.type === "group" && <span>→ {s.payload.folder}</span>}
        {s.type === "duplicate" && (
          <span>
            garder : {fileMap[s.payload.keep_id]?.name || `#${s.payload.keep_id}`}
          </span>
        )}
      </div>
      <div className="s-reason">{s.payload.reason}</div>
      {files.length > 0 && (
        <div className="s-files">
          {files.map((f) => (
            <div key={f.id} title={f.parent_dir}>
              {f.status === "deleted" ? "🗑 " : ""}
              {f.name}
            </div>
          ))}
        </div>
      )}
      <div className="s-actions">
        <button className="success" onClick={onApply} disabled={busy}>
          ✓ Appliquer
        </button>
        <button className="danger" onClick={onReject} disabled={busy}>
          ✕ Rejeter
        </button>
      </div>
    </div>
  );
}

export default function SortPanel({ notify, onChanged, refreshKey }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const fileMap = useFileNameMap(refreshKey);

  async function load() {
    setLoading(true);
    try {
      setSuggestions(await api.listSuggestions("pending"));
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [refreshKey]);

  async function recompute() {
    setLoading(true);
    try {
      const res = await api.recomputeSuggestions();
      await load();
      notify(`${res.suggestions_created} suggestion(s) recalculée(s).`, "success");
      onChanged();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setLoading(false);
    }
  }

  async function apply(id) {
    setBusyId(id);
    try {
      const res = await api.applySuggestion(id);
      notify(`Action appliquée : ${res.applied}`, "success");
      await load();
      onChanged();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(id) {
    setBusyId(id);
    try {
      await api.rejectSuggestion(id);
      await load();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusyId(null);
    }
  }

  const groups = {
    duplicate: suggestions.filter((s) => s.type === "duplicate"),
    group: suggestions.filter((s) => s.type === "group"),
    move: suggestions.filter((s) => s.type === "move"),
  };

  return (
    <>
      <div className="sb-section" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Tri proposé ({suggestions.length})</h3>
        <button onClick={recompute} disabled={loading} style={{ padding: "4px 10px" }}>
          ↻ Recalculer
        </button>
      </div>
      {loading && <div className="loading" style={{ padding: 16 }}>Chargement…</div>}
      {!loading && suggestions.length === 0 && (
        <div className="sb-section">
          <p style={{ color: "var(--text-dim)", fontSize: 12, margin: 0 }}>
            Aucune suggestion en attente. Lancez un scan ou cliquez sur
            « Recalculer ».
          </p>
        </div>
      )}
      {groups.duplicate.length > 0 && (
        <div className="sb-section">
          <h3>Doublons détectés</h3>
          {groups.duplicate.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              fileMap={fileMap}
              busy={busyId === s.id}
              onApply={() => apply(s.id)}
              onReject={() => reject(s.id)}
            />
          ))}
        </div>
      )}
      {groups.group.length > 0 && (
        <div className="sb-section">
          <h3>Regroupements proposés</h3>
          {groups.group.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              fileMap={fileMap}
              busy={busyId === s.id}
              onApply={() => apply(s.id)}
              onReject={() => reject(s.id)}
            />
          ))}
        </div>
      )}
      {groups.move.length > 0 && (
        <div className="sb-section">
          <h3>Déplacements</h3>
          {groups.move.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              fileMap={fileMap}
              busy={busyId === s.id}
              onApply={() => apply(s.id)}
              onReject={() => reject(s.id)}
            />
          ))}
        </div>
      )}
    </>
  );
}
