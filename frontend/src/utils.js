// Small shared helpers.

export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return "—";
  const units = ["o", "Ko", "Mo", "Go"];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(val >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function statusLabel(status) {
  const map = {
    unsorted: "À trier",
    sorted: "Trié",
    archived: "Archivé",
    deleted: "Corbeille",
    missing: "Manquant",
  };
  return map[status] || status;
}
