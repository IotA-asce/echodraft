import type { Job } from "../../api";
import { jobProgressMessage } from "../../lib/format";

export function ImportProgress({ job }: { job: Job | null }) {
  if (!job || !["queued", "running"].includes(job.status)) return null;
  return (
    <div className="chapter-progress import-progress" aria-live="polite">
      <div className="chapter-progress-row">
        <span>{jobProgressMessage(job, "Working locally")}</span>
        <span>{job.status}</span>
      </div>
      <progress aria-label="Manuscript import progress" className="chapter-progress-bar" />
      <p className="chapter-progress-detail">
        Keep this project open while Echodraft normalizes the manuscript. Page-aware PDFs and OCR can
        take a few minutes.
      </p>
    </div>
  );
}
