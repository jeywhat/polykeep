// Thin fetch wrapper. All endpoints are relative ("/api/..."); in dev the
// Vite proxy forwards them to FastAPI on :8000, in prod FastAPI serves both.

const BASE = "/api";

async function request(path, { method = "GET", body, parseJson = true } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  if (!parseJson) return res;
  return res.json();
}

export const api = {
  health: () => request("/health"),

  scan: () => request("/scan", { method: "POST" }),

  listFiles: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "")
        qs.set(k, v);
    });
    return request(`/files?${qs.toString()}`);
  },

  getFile: (id) => request(`/files/${id}`),

  openInStudio: (id) => request(`/files/${id}/open-info`),

  listFolders: () => request(`/folders`),

  moveFile: (id, targetDir) =>
    request(`/files/${id}/move`, { method: "POST", body: { target_dir: targetDir } }),

  deleteFile: (id) =>
    request(`/files/${id}/delete`, { method: "POST" }),

  addTag: (id, tag) =>
    request(`/files/${id}/tags`, { method: "POST", body: { tag } }),

  removeTag: (id, tagName) =>
    request(`/files/${id}/tags/${encodeURIComponent(tagName)}`, { method: "DELETE" }),

  listTags: () => request("/tags"),

  listSuggestions: (status = "pending") =>
    request(`/suggestions?status=${status}`),

  recomputeSuggestions: () =>
    request("/suggestions/recompute", { method: "POST" }),

  applySuggestion: (id) =>
    request(`/suggestions/${id}/apply`, { method: "POST" }),

  rejectSuggestion: (id) =>
    request(`/suggestions/${id}/reject`, { method: "POST" }),

  // Preview URLs
  stlUrl: (id) => `${BASE}/preview/stl/${id}`,
  modelUrl: (id) => `${BASE}/preview/model/${id}`,
  // Generic thumbnail (rendered STL PNG or extracted LYS image).
  thumbUrl: (id) => `${BASE}/preview/thumb/${id}`,
  lysThumbUrl: (id) => `${BASE}/preview/lys/${id}`,

  // Scan progress
  scanProgress: () => request("/scan/progress"),

  watchDirs: () => request("/imports/config"),
  saveWatchDirs: (paths) =>
    request("/imports/config", { method: "PUT", body: { paths } }),
  listImports: () => request("/imports"),
  importFiles: (sourcePaths, mode = "copy") =>
    request("/imports", { method: "POST", body: { source_paths: sourcePaths, mode } }),
  uploadImports: async (files, manifest) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file, file.name));
    form.append("manifest", JSON.stringify(manifest));
    const res = await fetch(`${BASE}/imports/upload`, { method: "POST", body: form });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    return res.json();
  },
};
