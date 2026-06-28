import type { RenderQueueItem, SegmentRenderComparison } from "../../api";

export function RenderQueuePanel({
  items,
  comparison,
}: {
  items: RenderQueueItem[];
  comparison: SegmentRenderComparison | null;
}) {
  return (
    <div className="render-workbench">
      <div className="source-heading">
        <strong>Render queue</strong>
        <span>{items.length ? `${items.filter((item) => item.status === "succeeded").length}/${items.length} succeeded` : "No queued renders"}</span>
      </div>
      {items.length ? (
        <div className="render-queue-list">
          {items.slice(0, 8).map((item) => (
            <article className={`render-queue-item ${item.status}`} key={item.id}>
              <div>
                <strong>{item.status.replaceAll("_", " ")}</strong>
                <small>
                  {item.provider} · {item.segmentId}
                </small>
              </div>
              {item.errorMessage ? <p>{item.errorMessage}</p> : <span>{item.renderKey ? item.renderKey.slice(0, 10) : "pending"}</span>}
            </article>
          ))}
        </div>
      ) : (
        <p className="import-placeholder">Produce a chapter to populate the local render queue.</p>
      )}
      <div className="render-compare">
        <strong>Render compare</strong>
        {comparison?.currentRender ? (
          <p>{comparison.previousRender ? `Changed: ${comparison.changedFields.length ? comparison.changedFields.join(", ") : "no request fields"}` : "Only one render exists for this segment."}</p>
        ) : (
          <p>Select Compare on a segment after it has render history.</p>
        )}
      </div>
    </div>
  );
}
