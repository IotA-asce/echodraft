import type { Direction, Segment, SegmentDirection, VoiceProfile } from "../../api";
import { DirectionControls } from "./DirectionControls";

export function SegmentEditorCard({
  segment,
  nextSegment,
  voices,
  editing,
  draft,
  savedDirection,
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
      <div className="segment-tools">
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
      <label className="override-label">
        Voice override
        <select defaultValue="" onChange={(event) => onOverride(segment.id, event.target.value)}>
          <option value="">Use project narrator</option>
          {voices.map((voice) => (
            <option key={voice.id} value={voice.id}>
              {voice.name}
            </option>
          ))}
        </select>
      </label>
      <DirectionControls segment={segment} saved={savedDirection} onSave={onSaveDirection} />
    </div>
  );
}
