import type { Chapter, Job, ProductionStatus, TtsSettings } from "../../api";

export function StudioHero({
  tts,
  setupJob,
  job,
  selectedChapter,
  status,
}: {
  tts: TtsSettings | null;
  setupJob: Job | null;
  job: Job | null;
  selectedChapter: Chapter | null;
  status: ProductionStatus | null;
}) {
  return (
    <>
      <header className="masthead">
        <a className="wordmark" href="#top">
          <span className="wordmark-mark">e</span>
          <span>echodraft</span>
        </a>
        <p>{tts?.ready ? `${tts.provider} local runtime ready` : "TTS needs local setup"}</p>
      </header>
      <section className="hero studio-hero" id="top">
        <div>
          <p className="eyebrow">The production desk</p>
          <h1>
            Stories, prepared
            <br />
            for their next voice.
          </h1>
          <p className="lede">A local, segment-first studio for shaping a manuscript into a reviewable audiobook draft.</p>
        </div>
        <aside className="status-card">
          <span className="pulse" />
          <div>
            <p>Production status</p>
            <strong>
              {setupJob?.status === "running"
                ? `Kokoro setup: ${String(setupJob.progress.phase ?? "working")}`
                : job?.status === "running"
                  ? `Producing: ${String(job.progress.phase ?? "working")}`
                  : selectedChapter
                    ? `${status?.currentSegments ?? 0}/${status?.totalSegments ?? 0} segments current`
                    : "Choose a chapter"}
            </strong>
          </div>
          <small>Files, renders, manifests, and exports remain on this machine.</small>
        </aside>
      </section>
    </>
  );
}
