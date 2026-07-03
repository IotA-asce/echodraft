import { useMemo, useState } from "react";
import type { StructureParserWarning } from "../../api";

type WarningFilter = "all" | "speaker" | "scene" | "mixed" | "cast" | "llm" | "errors";

const FILTERS: Array<{ id: WarningFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "speaker", label: "Needs speaker" },
  { id: "scene", label: "Scene breaks" },
  { id: "mixed", label: "Long / mixed segments" },
  { id: "cast", label: "Cast issues" },
  { id: "llm", label: "LLM issues" },
  { id: "errors", label: "Errors" },
];

export function StructureWarnings({ warnings }: { warnings: StructureParserWarning[] }) {
  const [filter, setFilter] = useState<WarningFilter>("all");
  const filtered = useMemo(
    () => warnings.filter((warning) => matchesFilter(warning, filter)),
    [filter, warnings],
  );
  return (
    <section className="structure-warning-panel" aria-label="Parser review items">
      <div className="structure-warning-heading">
        <strong>Parser Review</strong>
        <span>{warnings.length} open</span>
      </div>
      <div className="structure-warning-filters">
        {FILTERS.map((item) => (
          <button key={item.id} type="button" className={filter === item.id ? "active" : ""} onClick={() => setFilter(item.id)}>
            {item.label}
            <span>{warnings.filter((warning) => matchesFilter(warning, item.id)).length}</span>
          </button>
        ))}
      </div>
      {!warnings.length ? <p className="warning-empty">No parser review items.</p> : null}
      {warnings.length && !filtered.length ? <p className="warning-empty">No warnings in this category.</p> : null}
      {filtered.length ? (
        <div className="structure-warning-list">
          {filtered.map((warning) => {
            const code = textValue(warning.evidence.code, "uncoded");
            const action = textValue(warning.evidence.reviewAction, "review");
            const preview = textValue(warning.evidence.textPreview, "");
            const start = Number(warning.evidence.startOffset ?? warning.evidence.start_offset);
            const end = Number(warning.evidence.endOffset ?? warning.evidence.end_offset);
            return (
              <article key={warning.id}>
                <b>{warning.severity}</b>
                <span>{code}</span>
                <strong>{warning.message}</strong>
                <dl>
                  <div><dt>Action</dt><dd>{formatToken(action)}</dd></div>
                  {preview ? <div><dt>Preview</dt><dd>{preview}</dd></div> : null}
                  {Number.isFinite(start) && Number.isFinite(end) ? <div><dt>Offsets</dt><dd>{start}-{end}</dd></div> : null}
                  <div><dt>Confidence</dt><dd>{Math.round(warning.confidence * 100)}%</dd></div>
                  <div><dt>Scope</dt><dd>{warning.scopeType} · {warning.scopeId}</dd></div>
                </dl>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function matchesFilter(warning: StructureParserWarning, filter: WarningFilter) {
  const code = String(warning.evidence.code ?? "");
  if (filter === "all") return true;
  if (filter === "speaker") return code.includes("speaker") || code === "segment.dialogue_no_speaker";
  if (filter === "scene") return code.startsWith("scene.");
  if (filter === "mixed") return code.includes("mixed") || code.includes("multiple_speakers") || code.includes("long");
  if (filter === "cast") return code.startsWith("cast.");
  if (filter === "llm") return code.startsWith("llm.");
  return ["error", "blocking"].includes(warning.severity);
}

function textValue(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function formatToken(value: string) {
  return value.replaceAll("_", " ");
}
