import type { ChangeEvent } from "react";
import type { Job, SourceDocument, SourcePage, TextCleanlinessIssue } from "../../api";
import { EmptyState } from "../common/EmptyState";
import { ImportProgress } from "./ImportProgress";
import { SourcePreviewCard } from "./SourcePreviewCard";

export function ManuscriptIntakePanel({
  busy,
  importJob,
  source,
  pages,
  cleaningIssues,
  onChooseFile,
  onExtract,
  onReparse,
  onResolveCleaningIssue,
}: {
  busy: boolean;
  importJob: Job | null;
  source: SourceDocument | null;
  pages: SourcePage[];
  cleaningIssues: TextCleanlinessIssue[];
  onChooseFile: (event: ChangeEvent<HTMLInputElement>) => void;
  onExtract: () => void;
  onReparse: () => void;
  onResolveCleaningIssue: (issue: TextCleanlinessIssue) => Promise<void>;
}) {
  return (
    <section className="import-desk" aria-labelledby="manuscript-intake-title">
      <div>
        <p className="eyebrow">02 / Manuscript intake</p>
        <h2 id="manuscript-intake-title">Bring in the working text</h2>
        <p className="lede">TXT, Markdown, DOCX, EPUB, and PDF are normalized locally. Scanned PDF pages use local English OCR when Poppler and Tesseract are installed.</p>
      </div>
      <div className="import-card">
        <label className="drop-zone">
          <input aria-label="Manuscript file" type="file" accept=".txt,.md,.markdown,.docx,.epub,.pdf,application/pdf" onChange={onChooseFile} disabled={busy} />
          <strong>{busy ? "Working..." : "Choose a manuscript"}</strong>
          <span>Rights-confirmed local import · 10 MB maximum</span>
        </label>
        <ImportProgress job={importJob} />
        {source ? (
          <SourcePreviewCard
            source={source}
            pages={pages}
            cleaningIssues={cleaningIssues}
            busy={busy}
            onExtract={onExtract}
            onReparse={onReparse}
            onResolveCleaningIssue={onResolveCleaningIssue}
          />
        ) : (
          <EmptyState title="No manuscript imported." description="Choose a TXT, Markdown, DOCX, EPUB, or PDF file. The original stays on this machine." />
        )}
      </div>
    </section>
  );
}
