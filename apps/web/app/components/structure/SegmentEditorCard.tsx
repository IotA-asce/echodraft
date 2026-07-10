import { memo, useState } from "react";
import type { Direction, Segment, SegmentDirection, VoiceProfile } from "../../api";
import { DirectionControls } from "./DirectionControls";
import { Button, Drawer, Select } from "../../design-system";

// Memoized: this card is rendered once per visible (virtualized) segment row.
// Wrapping it means an unrelated top-level state change elsewhere in
// ProjectDashboard (a job poll tick, an unrelated panel's state) no longer
// forces every mounted card to re-render and re-diff its evidence/direction
// sub-tree — see docs/ui/frontend-architecture.md ("Root-Cause Analysis" #3).
// This only pays off if every prop below has a stable identity across
// unrelated renders, which is why the ~10 handlers passed in from
// `project-dashboard.tsx` are now wrapped in `useCallback`.
export const SegmentEditorCard = memo(function SegmentEditorCard({
  segment,
  nextSegment,
  voices,
  editing,
  draft,
  savedDirection,
  supportedDirection,
  busy,
  onStartEdit,
  onDraftChange,
  onCancelEdit,
  onSaveEdit,
  onToggleLock,
  onSplit,
  onMerge,
  onInspect,
  onOverride,
  onSaveDirection,
}: {
  segment: Segment;
  nextSegment?: Segment;
  voices: VoiceProfile[];
  editing: Segment | null;
  draft: string;
  savedDirection?: SegmentDirection;
  supportedDirection?: string[] | null;
  busy: boolean;
  onStartEdit: (segment: Segment) => void;
  onDraftChange: (value: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onToggleLock: (segment: Segment) => void;
  onSplit: (segment: Segment) => void;
  onMerge: (segment: Segment, nextSegment: Segment) => void;
  onInspect: (segmentId: string) => void;
  onOverride: (segmentId: string, voiceId: string) => void;
  onSaveDirection: (segmentId: string, direction: Direction) => Promise<void>;
}) {
  const isEditing = editing?.id === segment.id;
  const [showWhy, setShowWhy] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const evidence = segment.parserEvidence ?? {};
  const productionType = String(evidence.productionType ?? segment.segmentType ?? "narration");
  const speakerRule = typeof evidence.speakerRule === "string" ? evidence.speakerRule : null;
  const reviewAction = typeof evidence.reviewAction === "string" ? evidence.reviewAction : segment.status !== "ready" ? "review" : null;
  const sources = Array.isArray(evidence.sources) ? evidence.sources.map(String).slice(0, 2).join(" + ") : "structure";
  const atomIds = Array.isArray(evidence.atomIds) ? evidence.atomIds.map(String) : [];
  const sourceSpan = typeof evidence.sourceSpanId === "string" ? evidence.sourceSpanId : "";
  const readableEvidence = readableEvidenceText(evidence);
  return (
    <div className="segment-entry">
      <button
        className={isEditing ? "segment-button editing" : "segment-button"}
        type="button"
        onClick={() => onStartEdit(segment)}
      >
        <span>{segment.textContent}</span>
        <small>
          r{segment.revision} · {(segment.segmentType ?? "narration").replaceAll("_", " ")} · {segment.speakerCandidate || "narration"}
          {segment.userLocked ? " · locked" : ""}
        </small>
      </button>
      <div className="segment-evidence">
        <span>{productionType.replaceAll("_", " ")}</span>
        <span>{segment.speakerCandidate ? `${segment.speakerCandidate} · ${Math.round(segment.speakerConfidence * 100)}%` : "speaker unresolved"}</span>
        {speakerRule ? <span>{speakerRule.replaceAll("_", " ")}</span> : null}
        <span>{sources.replaceAll("_", " ")}</span>
        {reviewAction ? <span className="review-action">{reviewAction.replaceAll("_", " ")}</span> : null}
      </div>
      <div className="segment-tools">
        <button type="button" className="small-button" onClick={() => setShowWhy((current) => !current)}>
          Why?
        </button>
        <button type="button" className="small-button" onClick={() => onToggleLock(segment)}>
          {segment.userLocked ? "Unlock" : "Lock"}
        </button>
        <button type="button" className="small-button" disabled={segment.userLocked || segment.textContent.length < 40} onClick={() => onSplit(segment)}>
          Split
        </button>
        <button type="button" className="small-button" disabled={segment.userLocked || !nextSegment || nextSegment.userLocked} onClick={() => nextSegment && onMerge(segment, nextSegment)}>
          Merge next
        </button>
        <button type="button" className="small-button" onClick={() => onInspect(segment.id)}>
          Inspect
        </button>
      </div>
      {showWhy ? (
        <div className="segment-why-panel">
          <dl>
            <div><dt>Production type</dt><dd>{formatToken(productionType)}</dd></div>
            <div><dt>Stored type</dt><dd>{formatToken(segment.segmentType)}</dd></div>
            <div><dt>Speaker</dt><dd>{segment.speakerCandidate || "unresolved"}</dd></div>
            <div><dt>Speaker confidence</dt><dd>{Math.round(Number(segment.speakerConfidence ?? 0) * 100)}%</dd></div>
            <div><dt>Speaker rule</dt><dd>{speakerRule ? formatToken(speakerRule) : "none"}</dd></div>
            <div><dt>Status</dt><dd>{formatToken(segment.status)}</dd></div>
            <div><dt>Source</dt><dd>{sources.replaceAll("_", " ")}</dd></div>
            <div><dt>Atom IDs</dt><dd>{atomIds.length ? atomIds.join(", ") : "none"}</dd></div>
            <div><dt>Source span</dt><dd>{sourceSpan || "none"}</dd></div>
            <div><dt>Review action</dt><dd>{reviewAction ? formatToken(reviewAction) : "none"}</dd></div>
            <div><dt>Evidence</dt><dd>{readableEvidence}</dd></div>
          </dl>
          <Button type="button" variant="ghost" size="sm" onClick={() => setShowRaw(true)}>Raw parser evidence</Button>
          <Drawer open={showRaw} onOpenChange={setShowRaw} title="Raw parser evidence" description={`Evidence recorded for segment ${segment.id}.`} footer={<Button type="button" variant="secondary" onClick={() => setShowRaw(false)}>Close</Button>}><pre>{JSON.stringify(evidence, null, 2)}</pre></Drawer>
        </div>
      ) : null}
      {isEditing ? (
        <div className="segment-editor">
          <textarea aria-label="Narration text" value={draft} onChange={(event) => onDraftChange(event.target.value)} rows={6} />
          <p className="segment-editor-help">{draft !== editing.textContent ? `Saving creates revision r${editing.revision + 1}; revision r${editing.revision} remains in history.` : "Make a change to create a new revision."}</p>
          <div className="segment-editor-actions">
            <button className="secondary" type="button" onClick={onCancelEdit}>
              Cancel
            </button>
            <button type="button" disabled={busy || draft === editing.textContent} onClick={onSaveEdit}>
              Save revision
            </button>
          </div>
        </div>
      ) : null}
      <div className="override-label"><Select label="Voice override" value="" onValueChange={(value) => onOverride(segment.id, value)} options={[{ value: "", label: "Use project narrator" }, ...voices.map((voice) => ({ value: voice.id, label: voice.name }))]} /></div>
      <DirectionControls segment={segment} saved={savedDirection} supportedDirection={supportedDirection} onSave={onSaveDirection} />
    </div>
  );
});

function readableEvidenceText(evidence: Record<string, unknown>) {
  if (typeof evidence.speakerEvidence === "string" && evidence.speakerEvidence.trim()) return evidence.speakerEvidence;
  if (typeof evidence.llmEvidence === "string" && evidence.llmEvidence.trim()) return evidence.llmEvidence;
  const speakerEvidence = evidence.speakerEvidence;
  if (speakerEvidence && typeof speakerEvidence === "object" && "reason" in speakerEvidence) {
    return formatToken(String((speakerEvidence as { reason?: unknown }).reason ?? "parser evidence"));
  }
  if (typeof evidence.reason === "string" && evidence.reason.trim()) return formatToken(evidence.reason);
  return "Parser evidence was stored for this source span.";
}

function formatToken(value: string) {
  return value.replaceAll("_", " ");
}
