import type { SourceDocument, SourcePage, TextCleanlinessIssue } from "../../api";
import { CleanTextReview } from "./CleanTextReview";
import { ImportReview } from "./ImportReview";

export function SourcePreviewCard({
  source,
  pages,
  cleaningIssues,
  busy,
  onExtract,
  onReparse,
  onResolveCleaningIssue,
}: {
  source: SourceDocument;
  pages: SourcePage[];
  cleaningIssues: TextCleanlinessIssue[];
  busy: boolean;
  onExtract: () => void;
  onReparse: () => void;
  onResolveCleaningIssue: (issue: TextCleanlinessIssue) => Promise<void>;
}) {
  return (
    <div className="source-result">
      <div className="source-heading">
        <strong>{source.originalFilename}</strong>
        <span>
          <button type="button" onClick={onExtract} disabled={busy}>
            Extract structure
          </button>
          <button type="button" onClick={onReparse}>
            Reparse
          </button>
        </span>
      </div>
      <pre>{source.preview}</pre>
      <CleanTextReview issues={cleaningIssues} onResolve={onResolveCleaningIssue} />
      <ImportReview pages={pages} />
    </div>
  );
}
