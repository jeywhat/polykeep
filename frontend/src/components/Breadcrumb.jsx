import { breadcrumbSegments } from "../utils.js";

/**
 * Clickable breadcrumb of the current folder path.
 * Each crumb returns to that ancestor folder. The last crumb (current) is
 * shown as plain text, the others as links.
 */
export default function Breadcrumb({ folder, onNavigate }) {
  const crumbs = breadcrumbSegments(folder);
  return (
    <div className="breadcrumb">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={c.folder || "root"} className="crumb-wrap">
            {i > 0 && <span className="crumb-sep">›</span>}
            {last ? (
              <span className="crumb current">{c.label}</span>
            ) : (
              <button className="crumb" onClick={() => onNavigate(c.folder)}>
                {c.label}
              </button>
            )}
          </span>
        );
      })}
    </div>
  );
}
