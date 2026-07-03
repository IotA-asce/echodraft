import type { ReadinessReport } from "../../api";

export function ReadinessReportPanel({
  report,
  busy,
  onRun,
  onSetIssue,
}: {
  report: ReadinessReport | null;
  busy: boolean;
  onRun: () => Promise<void>;
  onSetIssue: (issueId: string, status: "resolved" | "ignored" | "locked") => Promise<void>;
}) {
  const active =
    report?.checks.filter(
      (check) =>
        check.status !== "passed" && (check.resolutionStatus == null || check.resolutionStatus === "open"),
    ) ?? [];
  const accepted =
    report?.checks.filter(
      (check) =>
        check.status !== "passed" &&
        (check.resolutionStatus === "ignored" || check.resolutionStatus === "locked"),
    ) ?? [];
  return (
    <div className="readiness-panel">
      <div className="source-heading">
        <strong>Readiness Report</strong>
        <span>{report ? `${report.status.replaceAll("_", " ")} · ${report.score}%` : "Not run"}</span>
      </div>
      <button type="button" className="small-button" disabled={busy} onClick={() => void onRun()}>
        Run readiness QA
      </button>
      {report ? (
        <div className="readiness-summary">
          <span>{report.summary.passed ?? 0} passed</span>
          <span>{report.summary.warnings ?? 0} warnings</span>
          <span>{report.summary.blocking ?? 0} blocking</span>
          <span>{report.summary.accepted ?? 0} accepted</span>
        </div>
      ) : (
        <p className="import-placeholder">Run deterministic readiness QA before export.</p>
      )}
      {active.length ? (
        <div className="readiness-list">
          {active.slice(0, 10).map((check) => (
            <article className={`readiness-check ${check.severity}`} key={check.id}>
              <div>
                <b>{check.scope}</b>
                <strong>{check.title}</strong>
                <p>{check.description}</p>
                <small>{check.resolutionStatus ?? "open"}</small>
              </div>
              {check.issueId ? (
                <span>
                  <button type="button" className="small-button" onClick={() => void onSetIssue(check.issueId!, "resolved")}>
                    Resolve
                  </button>
                  <button type="button" className="small-button secondary" onClick={() => void onSetIssue(check.issueId!, "ignored")}>
                    Accept risk
                  </button>
                  <button type="button" className="small-button secondary" onClick={() => void onSetIssue(check.issueId!, "locked")}>
                    Lock
                  </button>
                </span>
              ) : null}
            </article>
          ))}
        </div>
      ) : report ? (
        <p className="import-placeholder">No active readiness findings.</p>
      ) : null}
      {accepted.length ? (
        <div className="readiness-list accepted-risks">
          <div className="source-heading">
            <strong>Accepted risks</strong>
            <span>{accepted.length} acknowledged, still failing</span>
          </div>
          {accepted.slice(0, 10).map((check) => (
            <article className={`readiness-check ${check.severity} accepted`} key={check.id}>
              <div>
                <b>{check.scope}</b>
                <strong>{check.title}</strong>
                <p>{check.description}</p>
                <small>{check.resolutionStatus ?? "ignored"}</small>
              </div>
              {check.issueId ? (
                <span>
                  <button type="button" className="small-button" onClick={() => void onSetIssue(check.issueId!, "resolved")}>
                    Resolve
                  </button>
                </span>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </div>
  );
}
