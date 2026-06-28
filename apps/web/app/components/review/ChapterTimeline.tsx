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
  return (
    <div className="chapter-timeline">
      <div className="source-heading">
        <strong>Chapter timeline</strong>
        <span>{segments.length} lines</span>
      </div>
      <div className="timeline-list">
        {segments.length ? (
          segments.map((segment, index) => {
            const issueCount = issues.filter((issue) => issue.segmentId === segment.id).length;
            return (
              <button className={inspector?.segment.id === segment.id ? "timeline-item active" : "timeline-item"} type="button" key={segment.id} onClick={() => onInspect(segment.id)}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{segment.speakerCandidate || "Narration"}</strong>
                <small>
                  r{segment.revision} · {segment.segmentType.replaceAll("_", " ")}
                  {issueCount ? ` · ${issueCount} issue${issueCount === 1 ? "" : "s"}` : ""}
                </small>
              </button>
            );
          })
        ) : (
          <p className="import-placeholder">Open a chapter from the Story Map to review line timing.</p>
        )}
      </div>
    </div>
  );
}
