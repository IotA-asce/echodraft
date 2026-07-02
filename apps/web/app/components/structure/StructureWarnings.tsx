import type { StructureParserWarning } from "../../api";

export function StructureWarnings({ warnings }: { warnings: StructureParserWarning[] }) {
  if (!warnings.length) return null;
  return (
    <div className="structure-warning-list">
      {warnings.slice(0, 6).map((warning) => (
        <article key={warning.id}>
          <b>{warning.severity}</b>
          <strong>{warning.message}</strong>
          <small>
            {warning.scopeType} · {Math.round(warning.confidence * 100)}% confidence
          </small>
        </article>
      ))}
    </div>
  );
}
