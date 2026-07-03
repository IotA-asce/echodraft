import { useMemo, useState } from "react";
import type { Issue, StructureParserWarning } from "../../api";

type WarningFilter = "all" | "speaker" | "scene" | "mixed" | "cast" | "llm" | "errors";
type ReviewRow = {
  id: string;
  severity: string;
  code: string;
  title: string;
  description?: string;
  action: string;
  confidence: number;
  scope: string;
  kind: "warning" | "cast";
  details: Array<{ label: string; value: string }>;
};

const FILTERS: Array<{ id: WarningFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "speaker", label: "Needs speaker" },
  { id: "scene", label: "Scene breaks" },
  { id: "mixed", label: "Long / mixed segments" },
  { id: "cast", label: "Cast issues" },
  { id: "llm", label: "LLM issues" },
  { id: "errors", label: "Errors" },
];

const CAST_REVIEW_CODES = new Set(["cast.possible_duplicate", "cast.low_confidence_candidate"]);

export function StructureWarnings({
  warnings,
  issues = [],
}: {
  warnings: StructureParserWarning[];
  issues?: Issue[];
}) {
  const [filter, setFilter] = useState<WarningFilter>("all");
  const rows = useMemo(
    () => [
      ...warnings.map(warningRow),
      ...issues.filter(isCastReviewIssue).map(castIssueRow),
    ],
    [issues, warnings],
  );
  const filtered = useMemo(
    () => rows.filter((row) => matchesFilter(row, filter)),
    [filter, rows],
  );
  return (
    <section className="structure-warning-panel" aria-label="Parser review items">
      <div className="structure-warning-heading">
        <strong>Parser Review</strong>
        <span>{rows.length} open</span>
      </div>
      <div className="structure-warning-filters">
        {FILTERS.map((item) => (
          <button key={item.id} type="button" className={filter === item.id ? "active" : ""} onClick={() => setFilter(item.id)}>
            {item.label}
            <span>{rows.filter((row) => matchesFilter(row, item.id)).length}</span>
          </button>
        ))}
      </div>
      {!rows.length ? <p className="warning-empty">No parser review items.</p> : null}
      {rows.length && !filtered.length ? <p className="warning-empty">No warnings in this category.</p> : null}
      {filtered.length ? (
        <div className="structure-warning-list">
          {filtered.map((row) => (
            <article key={row.id}>
              <b>{row.severity}</b>
              <span>{row.code}</span>
              <strong>{row.title}</strong>
              {row.description ? <p>{row.description}</p> : null}
              <dl>
                <div><dt>Action</dt><dd>{formatToken(row.action)}</dd></div>
                {row.details.map((detail) => (
                  <div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>
                ))}
                <div><dt>Confidence</dt><dd>{Math.round(row.confidence * 100)}%</dd></div>
                <div><dt>Scope</dt><dd>{row.scope}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function warningRow(warning: StructureParserWarning): ReviewRow {
  const code = textValue(warning.evidence.code, "uncoded");
  const action = textValue(warning.evidence.reviewAction, "review");
  const preview = textValue(warning.evidence.textPreview, "");
  const start = Number(warning.evidence.startOffset ?? warning.evidence.start_offset);
  const end = Number(warning.evidence.endOffset ?? warning.evidence.end_offset);
  const details: Array<{ label: string; value: string }> = [];
  if (preview) details.push({ label: "Preview", value: preview });
  if (Number.isFinite(start) && Number.isFinite(end)) {
    details.push({ label: "Offsets", value: `${start}-${end}` });
  }
  return {
    id: warning.id,
    severity: warning.severity,
    code,
    title: warning.message,
    action,
    confidence: warning.confidence,
    scope: `${warning.scopeType} · ${warning.scopeId}`,
    kind: "warning",
    details,
  };
}

function castIssueRow(issue: Issue): ReviewRow {
  const metadata = issue.metadata ?? {};
  const code = textValue(metadata.code, "cast.issue");
  const possibleMatches = Array.isArray(metadata.possibleMatches)
    ? metadata.possibleMatches.map(String).filter(Boolean).join(", ")
    : "";
  const confidence = Number(metadata.confidence);
  const details = [
    { label: "Candidate", value: textValue(metadata.candidateName, "unknown") },
    ...(possibleMatches ? [{ label: "Possible matches", value: possibleMatches }] : []),
  ];
  return {
    id: issue.id,
    severity: issue.severity,
    code,
    title: issue.title,
    description: issue.description,
    action: textValue(metadata.reviewAction, "review_cast"),
    confidence: Number.isFinite(confidence) ? confidence : 0,
    scope: issue.segmentId ? `segment · ${issue.segmentId}` : issue.chapterId ? `chapter · ${issue.chapterId}` : "project",
    kind: "cast",
    details,
  };
}

function isCastReviewIssue(issue: Issue) {
  return (
    issue.status === "open"
    && issue.category === "cast_discovery"
    && CAST_REVIEW_CODES.has(String(issue.metadata?.code ?? ""))
  );
}

function matchesFilter(row: ReviewRow, filter: WarningFilter) {
  const code = row.code;
  if (filter === "all") return true;
  if (filter === "speaker") return code.includes("speaker") || code === "segment.dialogue_no_speaker";
  if (filter === "scene") return code.startsWith("scene.");
  if (filter === "mixed") return code.includes("mixed") || code.includes("multiple_speakers") || code.includes("long");
  if (filter === "cast") return row.kind === "cast" || code.startsWith("cast.");
  if (filter === "llm") return code.startsWith("llm.");
  return ["error", "blocking"].includes(row.severity);
}

function textValue(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function formatToken(value: string) {
  return value.replaceAll("_", " ");
}
