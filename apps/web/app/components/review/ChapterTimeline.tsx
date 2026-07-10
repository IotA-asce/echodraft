import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Issue, Segment, SegmentReviewInspector } from "../../api";

export function ChapterTimeline({
  segments,
  issues,
  inspector,
  onInspect,
}: {
  segments: Segment[];
  issues: Issue[];
  inspector: SegmentReviewInspector | null;
  onInspect: (segmentId: string) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const issueCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const issue of issues) if (issue.segmentId) counts.set(issue.segmentId, (counts.get(issue.segmentId) ?? 0) + 1);
    return counts;
  }, [issues]);
  // TanStack Virtual intentionally owns mutable scroll state; React Compiler skips this component.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({ count: segments.length, getScrollElement: () => scrollRef.current, estimateSize: () => 64, getItemKey: (index) => segments[index]?.id ?? index, overscan: 6, useFlushSync: false });
  return (
    <div className="chapter-timeline">
      <div className="source-heading">
        <strong>Chapter timeline</strong>
        <span>{segments.length} lines</span>
      </div>
      <div ref={scrollRef} className="timeline-list" data-testid="virtual-chapter-timeline">
        {segments.length ? (
          <div className="virtual-list-canvas" style={{ height: `${virtualizer.getTotalSize()}px` }}>{virtualizer.getVirtualItems().map((row) => {
            const segment = segments[row.index];
            if (!segment) return null;
            const issueCount = issueCounts.get(segment.id) ?? 0;
            return <div key={row.key} data-index={row.index} ref={virtualizer.measureElement} className="virtual-list-row" style={{ transform: `translateY(${row.start}px)` }}>
              <button className={inspector?.segment.id === segment.id ? "timeline-item active" : "timeline-item"} type="button" onClick={() => onInspect(segment.id)}>
                <span>{String(row.index + 1).padStart(2, "0")}</span>
                <strong>{segment.speakerCandidate || "Narration"}</strong>
                <small>
                  r{segment.revision} · {segment.segmentType.replaceAll("_", " ")}
                  {issueCount ? ` · ${issueCount} issue${issueCount === 1 ? "" : "s"}` : ""}
                </small>
              </button>
            </div>;
          })}</div>
        ) : (
          <p className="import-placeholder">Open a chapter from the Story Map to review line timing.</p>
        )}
      </div>
    </div>
  );
}
