import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { assetUrl, type ChapterReviewTimeline, type Issue, type SegmentReviewInspector, type TtsProvider } from "../../api";
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
  provider,
  onInspect,
  onOpenIssue,
}: {
  timeline: ChapterReviewTimeline | null;
  inspector: SegmentReviewInspector | null;
  issues: Issue[];
  provider?: TtsProvider;
  onInspect: (segmentId: string) => void;
  onOpenIssue: (issue: Issue) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const issueById = useMemo(() => new Map(issues.map((issue) => [issue.id, issue])), [issues]);
  const render = timeline?.chapterRender ?? null;
  const durationMs = Math.max(1, timeline?.durationMs ?? render?.durationMs ?? 0);
  // TanStack Virtual intentionally owns mutable scroll state; React Compiler skips this component.
  // eslint-disable-next-line react-hooks/incompatible-library
  const transcriptVirtualizer = useVirtualizer({ count: timeline?.segments.length ?? 0, getScrollElement: () => transcriptRef.current, estimateSize: () => 78, getItemKey: (index) => timeline?.segments[index]?.id ?? index, overscan: 6, useFlushSync: false });

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
      {render?.audioUrl ? (
        <article className="chapter-audio-player transcript-audio-player" aria-label="Active chapter audio">
          <div className="chapter-audio-heading">
            <div>
              <p className="eyebrow">Active chapter audio</p>
              <h3>{render.renderMode === "clean" ? "Clean narration" : `${render.renderMode} chapter mix`}</h3>
            </div>
            <small>{formatDuration(durationMs)}</small>
          </div>
          <audio ref={audioRef} controls src={assetUrl(render.audioUrl)} className="audio-player" />
          {provider === "mock" ? <p className="chapter-audio-note">Mock voice engine creates silent workflow audio.</p> : null}
        </article>
      ) : <p className="import-placeholder">No chapter audio yet.</p>}
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
      <div ref={transcriptRef} className="transcript-lines" data-testid="virtual-transcript-lines">
        <div className="virtual-list-canvas" style={{ height: `${transcriptVirtualizer.getTotalSize()}px` }}>{transcriptVirtualizer.getVirtualItems().map((row) => {
          const segment = timeline.segments[row.index];
          if (!segment) return null;
          const speaker = segment.speaker || "Narration";
          const hue = speakerHue(speaker);
          return <div key={row.key} data-index={row.index} ref={transcriptVirtualizer.measureElement} className="virtual-list-row" style={{ transform: `translateY(${row.start}px)` }}>
            <button
              className={inspector?.segment.id === segment.id ? "transcript-line active" : "transcript-line"}
              type="button"
              style={{ borderLeftColor: `hsl(${hue} 48% 42%)` }}
              onClick={() => jumpTo(segment.startMs, segment.id)}
            >
              <span className="transcript-time">{formatDuration(segment.startMs)}</span>
              <span className="speaker-chip" style={{ backgroundColor: `hsl(${hue} 42% 88%)`, color: `hsl(${hue} 44% 24%)` }}>{speaker}</span>
              <span className="transcript-text">{segment.text}</span>
              {segment.issueMarkers.length ? <span className="transcript-issues">{segment.issueMarkers.length} issue{segment.issueMarkers.length === 1 ? "" : "s"}</span> : null}
            </button>
          </div>;
        })}</div>
      </div>
    </div>
  );
}
