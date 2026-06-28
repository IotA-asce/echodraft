import { assetUrl, type Chapter, type Job, type ProductionStatus, type TtsSettings } from "../../api";
import { chapterJobProgress, formatDuration } from "../../lib/format";

export function ChapterAudioPlayer({
  chapter,
  activeRender,
  job,
  provider,
}: {
  chapter: Chapter;
  activeRender?: ProductionStatus["activeRender"];
  job: Job | null;
  provider?: TtsSettings["provider"];
}) {
  const progress = chapterJobProgress(job);
  const renderMode = activeRender?.renderMode ? activeRender.renderMode.replaceAll("_", " ") : "speech only";
  return (
    <article className="chapter-audio-player" aria-label="Active chapter audio">
      <div className="chapter-audio-heading">
        <div>
          <p className="eyebrow">Active chapter audio</p>
          <h3>{chapter.title || "Untitled chapter"}</h3>
        </div>
        <small>{activeRender ? `${renderMode} · ${formatDuration(activeRender.durationMs)}` : "No active render"}</small>
      </div>
      {progress ? (
        <div className="chapter-progress" aria-live="polite">
          <div className="chapter-progress-row">
            <span>{progress.label}</span>
            <span>{progress.percent}%</span>
          </div>
          <progress aria-label="Chapter production progress" className="chapter-progress-bar" value={progress.percent} max={100} />
          <p className="chapter-progress-detail">{progress.detail}</p>
        </div>
      ) : activeRender?.audioUrl ? (
        <>
          <audio controls src={assetUrl(activeRender.audioUrl)} className="audio-player" />
          {provider === "mock" ? <p className="chapter-audio-note">Mock voice engine creates silent workflow audio.</p> : null}
        </>
      ) : (
        <p className="import-placeholder">Produce this chapter to create playable audio.</p>
      )}
    </article>
  );
}
