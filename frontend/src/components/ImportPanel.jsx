import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

const KEYWORDS = ["stl", "obj", "figurine", "miniature", "terrain", "vehicle", "warhammer", "dnd"];

function formatSize(size) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} Ko`;
  return `${(size / 1024 / 1024).toFixed(1)} Mo`;
}

function suggestedTags(name, path) {
  const text = `${name} ${path}`.toLowerCase();
  const tags = KEYWORDS.filter((word) => text.includes(word));
  if (text.includes("makerworld")) tags.push("Makerworld");
  if (text.includes("thingiverse")) tags.push("Thingiverse");
  return [...new Set(tags)];
}

function parentOf(path) {
  const parts = path.replaceAll("\\", "/").split("/");
  parts.pop();
  return parts.join("/");
}

async function filesFromEntry(entry) {
  if (entry.isFile) {
    return new Promise((resolve) => entry.file((file) => resolve([{ file, relativePath: entry.fullPath.slice(1) }] )));
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const entries = [];
  let batch;
  do {
    batch = await new Promise((resolve) => reader.readEntries(resolve));
    entries.push(...batch);
  } while (batch.length);
  const nested = await Promise.all(entries.map(filesFromEntry));
  return nested.flat();
}

async function droppedFiles(event) {
  const entries = [...(event.dataTransfer?.items || [])]
    .map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.length) return (await Promise.all(entries.map(filesFromEntry))).flat();
  return [...(event.dataTransfer?.files || [])].map((file) => ({
    file, relativePath: file.webkitRelativePath || file.name,
  }));
}

export default function ImportPanel({ notify, onImported }) {
  const inputRef = useRef(null);
  const [paths, setPaths] = useState([]);
  const [pathText, setPathText] = useState("");
  const [serverItems, setServerItems] = useState([]);
  const [localItems, setLocalItems] = useState([]);
  const [destinationRule, setDestinationRule] = useState(() => localStorage.getItem("polykeep-import-destination") || "Importés");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [config, discovered] = await Promise.all([api.watchDirs(), api.listImports()]);
      setPaths(config.paths);
      setServerItems(discovered);
    } catch (error) { notify(error.message, "error"); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);
  useEffect(() => { localStorage.setItem("polykeep-import-destination", destinationRule); }, [destinationRule]);

  function addLocalFiles(found) {
    const supported = /\.(stl|lys|obj|ply|3mf|gltf|glb|fbx|dae|amf)$/i;
    const next = found.filter(({ file }) => supported.test(file.name)).map(({ file, relativePath }) => ({
      id: `${relativePath}-${file.size}-${file.lastModified}`,
      file, relativePath, name: file.name,
      destination: destinationRule,
      tags: suggestedTags(file.name, relativePath),
    }));
    setLocalItems((previous) => {
      const ids = new Set(previous.map((item) => item.id));
      return [...previous, ...next.filter((item) => !ids.has(item.id))];
    });
  }

  async function handleDrop(event) {
    event.preventDefault(); setDragging(false);
    addLocalFiles(await droppedFiles(event));
  }

  async function chooseFolder() {
    if (window.showDirectoryPicker) {
      try {
        const handle = await window.showDirectoryPicker();
        const found = [];
        async function visit(directory, prefix = "") {
          for await (const [name, child] of directory.entries()) {
            if (child.kind === "file") found.push({ file: await child.getFile(), relativePath: `${prefix}${name}` });
            else await visit(child, `${prefix}${name}/`);
          }
        }
        await visit(handle);
        addLocalFiles(found);
        return;
      } catch (error) { if (error.name === "AbortError") return; }
    }
    inputRef.current?.click();
  }

  function updateLocal(id, field, value) {
    setLocalItems((items) => items.map((item) => item.id === id ? { ...item, [field]: value } : item));
  }

  async function savePaths() {
    try {
      const next = pathText.split(/[\r\n,]+/).map((path) => path.trim()).filter(Boolean);
      const config = await api.saveWatchDirs(next);
      setPaths(config.paths); setPathText(""); await load();
      notify("Répertoires surveillés enregistrés.", "success");
    } catch (error) { notify(error.message, "error"); }
  }

  async function validateLocal() {
    if (!localItems.length) return;
    setBusy(true);
    try {
      const manifest = localItems.map((item) => ({
        name: item.name, destination: item.destination,
        tags: item.tags.split ? item.tags.split(",").map((tag) => tag.trim()).filter(Boolean) : item.tags,
      }));
      const result = await api.uploadImports(localItems.map((item) => item.file), manifest);
      setLocalItems([]); await load(); await onImported();
      const suffix = result.errors.length ? ` Échecs : ${result.errors.slice(0, 3).join(" | ")}` : "";
      notify(`${result.imported} fichier(s) importé(s).${suffix}`, result.errors.length ? "error" : "success");
    } catch (error) { notify(error.message, "error"); }
    finally { setBusy(false); }
  }

  async function importServer(path) {
    try {
      const result = await api.importFiles([path], "copy");
      await load(); await onImported();
      notify(`${result.imported} fichier importé, ${result.skipped} ignoré.`, "success");
    } catch (error) { notify(error.message, "error"); }
  }

  return (
    <section className="import-panel">
      <div className="import-header"><div><h2>Importer des fichiers</h2><p>Déposez un dossier, vérifiez les propositions, puis validez.</p></div><button onClick={load} disabled={loading}>Actualiser</button></div>
      <div className={`drop-zone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={handleDrop}>
        <strong>Déposez ici un dossier de modèles 3D</strong><span>Chrome / Edge · le sélecteur de dossier sert de fallback</span>
        <button type="button" className="primary" onClick={chooseFolder}>Choisir un dossier</button>
        <input ref={inputRef} type="file" webkitdirectory="true" directory="true" multiple hidden onChange={(event) => addLocalFiles([...event.target.files].map((file) => ({ file, relativePath: file.webkitRelativePath || file.name })))} />
      </div>
      <div className="import-settings"><strong>Règle de destination par défaut</strong><input value={destinationRule} onChange={(event) => setDestinationRule(event.target.value)} placeholder="Importés" /><small>Chemin relatif à /storage, modifiable fichier par fichier.</small></div>
      {localItems.length > 0 && <><div className="import-actions"><strong>Aperçu : {localItems.length} fichier(s)</strong><button className="primary" onClick={validateLocal} disabled={busy}>{busy ? "Import en cours…" : "Valider l’import"}</button><button onClick={() => setLocalItems([])}>Vider</button></div><div className="import-list">{localItems.map((item) => <div className="import-item import-edit" key={item.id}><span className="import-name"><strong>{item.relativePath}</strong><small>{formatSize(item.file.size)}</small></span><input value={item.destination} title="Destination" onChange={(event) => updateLocal(item.id, "destination", event.target.value)} /><input value={item.name} title="Nom final" onChange={(event) => updateLocal(item.id, "name", event.target.value)} /><input value={item.tags.join ? item.tags.join(", ") : item.tags} title="Tags" onChange={(event) => updateLocal(item.id, "tags", event.target.value)} /></div>)}</div></>}
      <div className="import-settings"><strong>Fallback : chemins locaux du serveur</strong>{paths.length > 0 && <ul>{paths.map((path) => <li key={path}>{path}</li>)}</ul>}<textarea value={pathText} onChange={(event) => setPathText(event.target.value)} placeholder="Un chemin par ligne" rows="2" /><button className="primary" onClick={savePaths}>Enregistrer</button></div>
      <div className="import-actions"><span>{serverItems.length} fichier(s) détecté(s) sur les répertoires surveillés</span></div>
      <div className="import-list">{serverItems.map((item) => <div className="import-item" key={item.source_path}><span className="import-name"><strong>{item.name}</strong><small>{item.source_dir}</small></span><span>{formatSize(item.size)}</span>{item.presumed_source && <span className="badge">{item.presumed_source}</span>}<button onClick={() => importServer(item.source_path)}>Importer</button></div>)}{!serverItems.length && !localItems.length && <div className="empty"><h2>Aucun fichier en attente</h2><p>Déposez un dossier ou configurez un chemin local côté serveur.</p></div>}</div>
    </section>
  );
}
