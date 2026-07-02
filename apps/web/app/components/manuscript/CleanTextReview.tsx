import type { TextCleanlinessIssue } from "../../api";

export function CleanTextReview({
  issues,
  onResolve,
}: {
  issues: TextCleanlinessIssue[];
  onResolve: (issue: TextCleanlinessIssue) => Promise<void>;
}) {
  if (!issues.length) return null;
  const openIssues = issues.filter((issue) => issue.status === "open");
  const applied = issues.filter((issue) => issue.status !== "open");
  return (
    <div className="clean-text-review">
      <div className="source-heading">
        <strong>Clean text review</strong>
        <span>
          {openIssues.length} open · {applied.length} applied
        </span>
      </div>
      <div className="clean-issue-list">
        {issues.map((issue) => (
          <article className={`clean-issue ${issue.status}`} key={issue.id}>
            <div>
              <b>{issue.severity}</b>
              <strong>{issue.issueType.replaceAll("_", " ")}</strong>
              <p>
                {issue.suggestedFix !== null && issue.suggestedFix !== undefined
                  ? `Suggested replacement: ${issue.suggestedFix || "remove marker"}`
                  : "Review this token in the canonical preview before structure extraction."}
              </p>
              <small>
                Offsets {issue.canonicalSpanStart}-{issue.canonicalSpanEnd} ·{" "}
                {Math.round(issue.confidence * 100)}% confidence
              </small>
            </div>
            {issue.status === "open" ? (
              <button type="button" className="small-button" onClick={() => void onResolve(issue)}>
                Mark reviewed
              </button>
            ) : (
              <span className="clean-status">{issue.status}</span>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
