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
}) {
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
    </div>
  );
}
