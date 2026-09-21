export function formatPlayTime(seconds: number): string {
  if (seconds <= 0) return "Not played";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours === 0 && minutes === 0) return "< 1m";
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
}

export function formatRelative(iso: string | null): string {
  if (!iso) return "Never";
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return date.toLocaleDateString();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

/**
 * Release dates from the game database are often only a year or a month; those
 * are stored as the 1st, so the 1st is shown with the precision it really has.
 */
export function formatReleaseDate(iso: string | null): string {
  if (!iso) return "Unknown";
  const [year, month, day] = iso.slice(0, 10).split("-");
  if (day !== "01") return formatDate(iso);
  if (month === "01") return year;
  return new Date(`${year}-${month}-01T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "short" });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "Unknown";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
