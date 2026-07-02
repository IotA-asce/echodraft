import { assetUrl, type SegmentRenderComparison, type SegmentReviewInspector } from "../../api";
import { arrayRecords, formatDuration, recordAt } from "../../lib/format";

export function SegmentInspectorPanel({
  inspector,
  comparison,
}: {
  inspector: SegmentReviewInspector | null;
  comparison: SegmentRenderComparison | null;
}) {
  if (!inspector) {
    return (
      <div className="segment-inspector empty">
        <div className="source-heading">
          <strong>Segment Inspector</strong>
          <span>No segment selected</span>
        </div>
        <p className="import-placeholder">Select Inspect on a segment to load review layers.</p>
      </div>
    );
  }
  const currentRender = comparison?.currentRender ?? inspector.renderHistory[0] ?? null;
  const structureSegment = recordAt(inspector.structure, "segment");
  const warnings = arrayRecords(inspector.structure.warnings);
  const durationMs = typeof inspector.waveform.durationMs === "number" ? inspector.waveform.durationMs : currentRender?.durationMs;
  return (
    <div className="segment-inspector">
      <div className="source-heading">
        <strong>Segment Inspector</strong>
        <span>
          {inspector.segment.segmentType.replaceAll("_", " ")} · r{inspector.segment.revision}
        </span>
      </div>
      <div className="inspector-grid">
        <section>
          <div className="inspector-layer-title">
            <b>Source</b>
            <span>{inspector.segment.id}</span>
          </div>
          <pre>{inspector.sourceText}</pre>
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Canonical</b>
            <span>{inspector.segment.status}</span>
          </div>
          <pre>{inspector.canonicalText}</pre>
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Structure</b>
            <span>{String(structureSegment.status ?? "unknown")}</span>
          </div>
          <div className="inspector-chips">
            <span>Chapter {String(recordAt(inspector.structure, "chapter").orderIndex ?? 0)}</span>
            <span>Scene {String(recordAt(inspector.structure, "scene").orderIndex ?? 0)}</span>
            <span>{Math.round(Number(structureSegment.speakerConfidence ?? 0) * 100)}% speaker</span>
            {inspector.segment.userLocked ? <span>Locked</span> : null}
          </div>
          {warnings.length ? <p>{warnings.length} parser warnings attached.</p> : <p>No parser warnings attached.</p>}
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Cast</b>
            <span>{inspector.cast?.status ?? "unassigned"}</span>
          </div>
          <p>{inspector.cast?.speakerName ?? inspector.segment.speakerCandidate ?? "Narrator"}</p>
          <small>
            {inspector.cast
              ? `${inspector.cast.method} · ${Math.round(inspector.cast.confidence * 100)}% confidence${inspector.cast.voiceProfileId ? " · voice linked" : ""}`
              : "No speaker attribution record."}
          </small>
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Direction</b>
            <span>{inspector.direction?.source ?? "default"}</span>
          </div>
          <p>
            {inspector.direction?.direction.emotion ?? "neutral"} · pace {inspector.direction?.direction.pace.toFixed(2) ?? "1.00"} · intensity{" "}
            {Math.round((inspector.direction?.direction.intensity ?? 0.4) * 100)}%
          </p>
          <small>{inspector.direction?.userLocked ? "locked" : inspector.direction?.directionFingerprint?.slice(0, 12) ?? "No saved direction."}</small>
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Waveform</b>
            <span>{formatDuration(durationMs)}</span>
          </div>
          {currentRender?.audioUrl ? <audio controls src={assetUrl(currentRender.audioUrl)} className="audio-player compact" /> : <p>No segment audio yet.</p>}
          <small>
            {inspector.waveform.sampleRate ? `${String(inspector.waveform.sampleRate)} Hz` : "sample rate pending"} ·{" "}
            {Array.isArray(inspector.waveform.waveform) ? inspector.waveform.waveform.length : 0} peaks
          </small>
        </section>
      </div>
      <div className="inspector-lists">
        <section>
          <div className="inspector-layer-title">
            <b>Render history</b>
            <span>{inspector.renderHistory.length}</span>
          </div>
          {inspector.renderHistory.length ? (
            inspector.renderHistory.slice(0, 5).map((render) => (
              <p key={render.id}>
                <span>{render.id}</span>
                <small>
                  {formatDuration(render.durationMs)} · {render.parentRenderId ? `parent ${render.parentRenderId}` : "root"}
                </small>
              </p>
            ))
          ) : (
            <p>No render history.</p>
          )}
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>QA</b>
            <span>{inspector.qaIssues.length}</span>
          </div>
          {inspector.qaIssues.length ? inspector.qaIssues.slice(0, 5).map((issue) => <p key={issue.id}><span>{issue.title}</span><small>{issue.severity} · {issue.status}</small></p>) : <p>No segment QA findings.</p>}
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Comments</b>
            <span>{inspector.comments.length}</span>
          </div>
          {inspector.comments.length ? inspector.comments.slice(0, 5).map((comment) => <p key={comment.id}>{comment.body}</p>) : <p>No local comments.</p>}
        </section>
        <section>
          <div className="inspector-layer-title">
            <b>Patch queue</b>
            <span>{inspector.patchQueue.length}</span>
          </div>
          {inspector.patchQueue.length ? inspector.patchQueue.slice(0, 5).map((patch) => <p key={patch.id}><span>{patch.newRenderId}</span><small>{patch.issueId ?? "manual patch"} · chapter {patch.chapterRenderId}</small></p>) : <p>No patch attempts.</p>}
        </section>
      </div>
    </div>
  );
}
