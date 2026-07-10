import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const directionBySegment = useMemo(() => new Map(directions.map((item) => [item.segmentId, item])), [directions]);
  // TanStack Virtual intentionally owns mutable scroll state; React Compiler skips this component.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 210,
    getItemKey: (index) => segments[index]?.id ?? index,
    overscan: 4,
    useFlushSync: false,
  });
  return (
    <div ref={scrollRef} className="segment-column virtual-scroll" data-testid="virtual-segment-list">
      <div className="virtual-list-canvas" style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map((row) => {
          const segment = segments[row.index];
          if (!segment) return null;
          return <div key={row.key} data-index={row.index} ref={virtualizer.measureElement} className="virtual-list-row" style={{ transform: `translateY(${row.start}px)` }}>
            <SegmentEditorCard segment={segment} nextSegment={segments[row.index + 1]} voices={voices} editing={editing} draft={draft} savedDirection={directionBySegment.get(segment.id)} supportedDirection={supportedDirection} busy={busy} onStartEdit={onStartEdit} onDraftChange={onDraftChange} onCancelEdit={onCancelEdit} onSaveEdit={onSaveEdit} onToggleLock={onToggleLock} onSplit={onSplit} onMerge={onMerge} onInspect={onInspect} onOverride={onOverride} onSaveDirection={onSaveDirection} />
          </div>;
        })}
      </div>
    </div>
  );
}
