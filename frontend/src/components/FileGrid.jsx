import FileCard from "./FileCard.jsx";
import { groupBySubfolder } from "../utils.js";

export default function FileGrid({ files, folder, onSelect, loading }) {
  if (loading) return <div className="loading">Chargement…</div>;
  if (!files?.length)
    return (
      <div className="empty">
        <h2>Aucun fichier</h2>
        <p>Aucun fichier dans ce dossier (ou lancez un scan pour indexer).</p>
      </div>
    );

  const groups = groupBySubfolder(files, folder);

  return (
    <div className="groups">
      {groups.map((g) =>
        g.kind === "root" ? (
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
                <FileCard key={f.id} file={f} folder={folder} onClick={onSelect} />
              ))}
            </div>
          </section>
        ) : (
          <section key={g.key} className="file-group">
            <h3 className="group-header" title={`${folder ? folder + "/" : ""}${g.label}`}>
              <span className="group-icon">📁</span>
              <span className="group-name">{g.label}</span>
              <span className="group-count">{g.files.length}</span>
            </h3>
            <div className="grid">
              {g.files.map((f) => (
                <FileCard key={f.id} file={f} folder={folder} onClick={onSelect} />
              ))}
            </div>
          </section>
        )
      )}
    </div>
  );
}
