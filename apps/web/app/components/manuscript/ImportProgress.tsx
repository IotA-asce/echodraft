import type { Job } from "../../api";
import { jobProgressMessage, jobProgressPercent } from "../../lib/format";

export function ImportProgress({
  job,
  label = "Manuscript import",
  detail = "Keep this project open while Echodraft normalizes the manuscript. Page-aware PDFs and OCR can take a few minutes.",
  progressLabel = "Manuscript import progress",
}: {
  job: Job | null;
  label?: string;
  detail?: string;
  progressLabel?: string;
}) {
  if (!job || !["queued", "running"].includes(job.status)) return null;
  const percent = jobProgressPercent(job);
  return (
    <div className="chapter-progress import-progress" aria-live="polite">
      <div className="chapter-progress-row">
        <span>{label}: {jobProgressMessage(job, "Working locally")}</span>
        <span>{percent === null ? job.status : `${percent}%`}</span>
      </div>
      <progress aria-label={progressLabel} className="chapter-progress-bar" value={percent ?? undefined} max={percent === null ? undefined : 100} />
      <p className="chapter-progress-detail">{detail}</p>
    </div>
  );
}
