export default function Toolbar({
  query,
  setQuery,
  status,
  setStatus,
  ext,
  setExt,
  tags,
  activeTag,
  setActiveTag,
  total,
  onScan,
  scanning,
  scanProgress,
  onScanControl,
}) {
  const showProgress = scanning && scanProgress;
  const phaseLabels = {
    idle: "En attente",
    discovery: "Découverte fichiers",
    db_upsert: "Indexation base de données",
    missing_mark: "Marquage manquants",
    thumbnails: "Génération vignettes",
    apply_results: "Finalisation",
    suggestions: "Suggestions",
    complete: "Terminé",
    error: "Erreur",
  };

  return (
    <div className="toolbar">
      <input
        type="text"
        placeholder="🔍 Rechercher (nom, dossier…)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">Tous statuts</option>
        <option value="unsorted">À trier</option>
        <option value="sorted">Trié</option>
        <option value="archived">Archivé</option>
        <option value="deleted">Corbeille</option>
        <option value="missing">Manquant</option>
      </select>
      <select value={ext} onChange={(e) => setExt(e.target.value)}>
        <option value="">Tous formats</option>
        <option value="stl">STL</option>
        <option value="lys">LYS</option>
        <option value="obj">OBJ</option>
        <option value="ply">PLY</option>
        <option value="3mf">3MF</option>
        <option value="gltf">GLTF</option>
        <option value="glb">GLB</option>
        <option value="fbx">FBX</option>
        <option value="dae">DAE</option>
        <option value="amf">AMF</option>
      </select>
      <select value={activeTag} onChange={(e) => setActiveTag(e.target.value)}>
        <option value="">Tous tags</option>
        {tags.map((t) => (
          <option key={t.name} value={t.name}>
            {t.name} ({t.count})
          </option>
        ))}
      </select>
      <span className="count">{total} fichiers</span>
      <button className="primary" onClick={onScan} disabled={scanning}>
        {scanning ? "Scan en cours…" : "⏻ Scanner"}
      </button>

      {showProgress && (
        <div className="scan-progress">
          <div className="progress-header">
            <span className="phase-label">
              {scanProgress.paused ? "En pause" : phaseLabels[scanProgress.phase] || scanProgress.phase}
            </span>
            <span className="progress-pct">{scanProgress.overall_progress.toFixed(1)}%</span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${scanProgress.overall_progress}%` }}
            />
          </div>
          <div className="progress-details">
            {scanProgress.phase_total_files > 0 && (
              <>
                <span>{scanProgress.processed_files}/{scanProgress.phase_total_files} fichiers</span>
                <span className="progress-current-file">{scanProgress.current_file}</span>
              </>
            )}
            {scanProgress.elapsed_seconds > 0 && (
              <span>⏱ {scanProgress.elapsed_seconds.toFixed(0)}s</span>
            )}
            {scanProgress.eta_seconds && (
              <span>⏳ ~{scanProgress.eta_seconds.toFixed(0)}s</span>
            )}
          </div>
          <div className="scan-actions">
            {scanProgress.paused ? (
              <button onClick={() => onScanControl("resume")}>▶ Reprendre</button>
            ) : (
              <button onClick={() => onScanControl("pause")}>Ⅱ Pause</button>
            )}
            <button className="danger" onClick={() => onScanControl("stop")}>■ Arrêter</button>
          </div>
          {scanProgress.error && (
            <div className="progress-error">Erreur: {scanProgress.error}</div>
          )}
        </div>
      )}
    </div>
  );
}
