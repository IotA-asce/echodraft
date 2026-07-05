import { useMemo, useRef } from "react";
import { assetUrl, type ChapterReviewTimeline, type Issue, type SegmentReviewInspector } from "../../api";
import { formatDuration } from "../../lib/format";

function speakerHue(speaker: string) {
  let hash = 0;
  for (let index = 0; index < speaker.length; index += 1) hash = (hash * 31 + speaker.charCodeAt(index)) % 360;
  return 25 + (hash % 270);
}

export function ChapterTranscriptReview({
  timeline,
  inspector,
  issues,
  onInspect,
  onOpenIssue,
}: {
  timeline: ChapterReviewTimeline | null;
  inspector: SegmentReviewInspector | null;
  issues: Issue[];
  onInspect: (segmentId: string) => void;
  onOpenIssue: (issue: Issue) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const issueById = useMemo(() => new Map(issues.map((issue) => [issue.id, issue])), [issues]);
  const render = timeline?.chapterRender ?? null;
  const durationMs = Math.max(1, timeline?.durationMs ?? render?.durationMs ?? 0);

  function jumpTo(startMs: number, segmentId?: string | null, issueId?: string | null) {
    if (audioRef.current) audioRef.current.currentTime = Math.max(0, startMs / 1000);
    if (segmentId) onInspect(segmentId);
    if (issueId) {
      const issue = issueById.get(issueId);
      if (issue) onOpenIssue(issue);
    }
  }

  if (!timeline) {
    return (
      <div className="transcript-review empty">
        <div className="source-heading">
          <strong>Dialogue transcript</strong>
          <span>No timeline</span>
        </div>
        <p className="import-placeholder">Produce a chapter to create a timed transcript review.</p>
      </div>
    );
  }

  return (
    <div className="transcript-review">
      <div className="source-heading">
        <strong>Dialogue transcript</strong>
        <span>{timeline.segments.length} lines - {formatDuration(durationMs)}</span>
      </div>
      {render?.audioUrl ? <audio ref={audioRef} controls src={assetUrl(render.audioUrl)} className="audio-player" /> : <p className="import-placeholder">No chapter audio yet.</p>}
      <div className="waveform-strip" aria-label="Chapter waveform with issue markers">
        {(timeline.waveform.length ? timeline.waveform : Array.from({ length: 80 }, () => 0)).map((peak, index) => (
          <button
            aria-label={`Jump to ${formatDuration(Math.round((index / Math.max(1, timeline.waveform.length)) * durationMs))}`}
            className="waveform-bar"
            key={`${index}-${peak}`}
            type="button"
            style={{ height: `${Math.max(8, Math.round(peak * 42))}px` }}
            onClick={() => jumpTo(Math.round((index / Math.max(1, timeline.waveform.length)) * durationMs))}
          />
        ))}
        {timeline.issueMarkers.map((marker) => (
          <button
            aria-label={`Jump to issue ${marker.title}`}
            className={`waveform-marker ${marker.severity}`}
            key={marker.id}
            type="button"
            style={{ left: `${Math.min(98, Math.max(0, (marker.startMs / durationMs) * 100))}%` }}
            title={marker.title}
            onClick={() => jumpTo(marker.startMs, marker.segmentId, marker.issueId)}
          />
        ))}
      </div>
      <div className="transcript-lines">
        {timeline.segments.map((segment) => {
          const speaker = segment.speaker || "Narration";
          const hue = speakerHue(speaker);
          return (
            <button
              className={inspector?.segment.id === segment.id ? "transcript-line active" : "transcript-line"}
              key={segment.id}
              type="button"
              style={{ borderLeftColor: `hsl(${hue} 48% 42%)` }}
              onClick={() => jumpTo(segment.startMs, segment.id)}
            >
              <span className="transcript-time">{formatDuration(segment.startMs)}</span>
              <span className="speaker-chip" style={{ backgroundColor: `hsl(${hue} 42% 88%)`, color: `hsl(${hue} 44% 24%)` }}>{speaker}</span>
              <span className="transcript-text">{segment.text}</span>
              {segment.issueMarkers.length ? <span className="transcript-issues">{segment.issueMarkers.length} issue{segment.issueMarkers.length === 1 ? "" : "s"}</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
