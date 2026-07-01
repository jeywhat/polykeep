import { formatSize, statusLabel, relativeDirLabel } from "../utils.js";
import { api } from "../api/client.js";

export default function FileCard({ file, folder, onClick }) {
  const isLys = file.ext === "lys";
  const relDir = relativeDirLabel(file.parent_dir, folder);
  return (
    <div className="card" onClick={() => onClick(file)}>
      <div className="thumb">
        {file.preview_url ? (
          <img src={api.thumbUrl(file.id)} alt={file.name} />
        ) : (
          <span className="ext-badge" style={{ color: isLys ? "var(--lys)" : "var(--stl)" }}>
            {file.ext}
          </span>
        )}
      </div>
      <div className="name" title={file.name}>
        {file.name}
      </div>
      {relDir && (
        <div className="card-dir" title={file.parent_dir}>
          {relDir}
        </div>
      )}
      <div className="meta">
        <span>
          <span className={`status-dot status-${file.status}`} />
          {statusLabel(file.status)}
        </span>
        <span>{formatSize(file.size)}</span>
      </div>
      {file.tags?.length > 0 && (
        <div className="tags">
          {file.tags.slice(0, 4).map((t) => (
            <span key={t} className="badge">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
