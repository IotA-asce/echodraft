import type { Direction, Segment, SegmentDirection, VoiceProfile } from "../../api";
import { SegmentEditorCard } from "./SegmentEditorCard";

export function SegmentList({
  segments,
  voices,
  editing,
  draft,
  directions,
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
  segments: Segment[];
  voices: VoiceProfile[];
  editing: Segment | null;
  draft: string;
  directions: SegmentDirection[];
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
  return (
    <div className="segment-column">
      {segments.map((segment, index) => (
        <SegmentEditorCard
          key={segment.id}
          segment={segment}
          nextSegment={segments[index + 1]}
          voices={voices}
          editing={editing}
          draft={draft}
          savedDirection={directions.find((item) => item.segmentId === segment.id)}
          supportedDirection={supportedDirection}
          busy={busy}
          onStartEdit={onStartEdit}
          onDraftChange={onDraftChange}
          onCancelEdit={onCancelEdit}
          onSaveEdit={onSaveEdit}
          onToggleLock={onToggleLock}
          onSplit={onSplit}
          onMerge={onMerge}
          onInspect={onInspect}
          onOverride={onOverride}
          onSaveDirection={onSaveDirection}
        />
      ))}
    </div>
  );
}
