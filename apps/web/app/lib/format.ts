import type { Job, LocalAiCatalogItem } from "../api";

export const structureStatusLabels: Record<string, string> = {
  draft: "Draft",
  structured: "Structured",
  unresolved: "Needs review",
};

export function formatStructureStatus(status: string, confidence: number) {
  const label =
    structureStatusLabels[status] ??
    status.replaceAll("_", " ").replace(/^\w/, (match) => match.toUpperCase());
  return `${label} · auto-structure confidence ${Math.round(confidence * 100)}%`;
}

export function formatDuration(durationMs?: number | null) {
  if (durationMs == null) return "Duration pending";
  const totalSeconds = Math.round(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function formatBytes(bytes?: number | null) {
  if (!bytes) return "Size pending";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function progressNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function chapterJobProgress(job: Job | null) {
  if (!job || !["queued", "running"].includes(job.status)) return null;
  const phase = typeof job.progress.phase === "string" ? job.progress.phase : "queued";
  const current = progressNumber(job.progress.current);
  const total = progressNumber(job.progress.total);
  const percent =
    total && current !== null
      ? Math.min(100, Math.max(0, Math.round((current / total) * 100)))
      : 0;
  const label =
    phase === "rendering" && current !== null && total
      ? `Rendering segment ${current}/${total}`
      : phase === "assembling"
        ? "Assembling chapter audio"
        : "Preparing chapter production";
  return { label, percent, detail: "Chapter production is running; audio will appear when complete." };
}

export function jobProgressMessage(job: Job, fallback: string) {
  if (typeof job.progress.message === "string") return job.progress.message;
  if (typeof job.progress.phase === "string") return job.progress.phase.replaceAll("_", " ");
  return fallback;
}

export function capabilityLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

export function modelStatus(item: LocalAiCatalogItem) {
  if (item.health === "ready") return "Ready";
  if (item.status === "failed") return "Failed";
  if (item.health === "missing") return "Missing";
  if (item.health === "unavailable") return "Unavailable";
  return item.status.replaceAll("_", " ");
}

export function recordAt(value: Record<string, unknown>, key: string): Record<string, unknown> {
  const child = value[key];
  return child && typeof child === "object" && !Array.isArray(child)
    ? (child as Record<string, unknown>)
    : {};
}

export function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}
