import { memo } from "react";
import type { Issue } from "../../api";
import { uiCopy } from "../../lib/copy";

// Memoized: rendered once per row in the (unbounded) issue list on the
// Review & Patch panel. Requires stable `onOpen`/`onPatch`/`onResolve`
// identities from the caller (see project-dashboard.tsx's
// `handleOpenIssue`/`handlePatchIssue`/`handleResolveIssue`).
export const IssueCard = memo(function IssueCard({
  issue,
  onOpen,
  onPatch,
  onResolve,
}: {
  issue: Issue;
  onOpen: (issue: Issue) => void;
  onPatch: (issue: Issue) => void;
  onResolve: (issue: Issue) => void;
}) {
  return (
    <article className="issue-card">
      <div>
        <b>{issue.severity}</b>
        <strong>{issue.title}</strong>
        <p>{issue.description}</p>
      </div>
      <span>
        <button type="button" className="small-button" onClick={() => onOpen(issue)}>
          Open discussion
        </button>
        {issue.segmentId ? (
          <button type="button" className="small-button" onClick={() => onPatch(issue)}>
            {uiCopy.fixThisLine}
          </button>
        ) : null}
        {issue.status !== "resolved" ? (
          <button type="button" className="small-button" onClick={() => onResolve(issue)}>
            Mark resolved
          </button>
        ) : null}
      </span>
    </article>
  );
});
