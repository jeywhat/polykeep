import FileCard from "./FileCard.jsx";

export default function FileGrid({ files, onSelect, loading }) {
  if (loading) return <div className="loading">Chargement…</div>;
  if (!files?.length)
    return (
      <div className="empty">
        <h2>Aucun fichier</h2>
        <p>Lancez un scan pour indexer vos fichiers 3D.</p>
      </div>
    );
  return (
    <div className="grid">
      {files.map((f) => (
        <FileCard key={f.id} file={f} onClick={onSelect} />
      ))}
    </div>
  );
}
