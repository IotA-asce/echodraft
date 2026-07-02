import type { Job, LocalAiCatalogItem, LocalAiInstallJob } from "../../api";
import { capabilityLabel, modelStatus, progressNumber } from "../../lib/format";

export function ModelCenter({
  catalog,
  job,
  installJob,
  busy,
  onInstall,
  onVerify,
}: {
  catalog: LocalAiCatalogItem[];
  job: Job | null;
  installJob: LocalAiInstallJob | null;
  busy: boolean;
  onInstall: (item: LocalAiCatalogItem) => Promise<void>;
  onVerify: (item: LocalAiCatalogItem) => Promise<void>;
}) {
  const required = catalog.filter((item) => item.required);
  const readyRequired = required.filter((item) => item.health === "ready").length;
  const running = job && ["queued", "running"].includes(job.status);
  const activeKey = installJob?.modelKey;
  const groups = ["pdf_rendering", "ocr", "local_llm_runtime", "local_llm", "embeddings", "tts", "audio_processing"];
  const ordered = [...catalog].sort((a, b) => groups.indexOf(a.capability) - groups.indexOf(b.capability));

  return (
    <section className="studio-section model-center">
      <div>
        <p className="eyebrow">00 / Model Center</p>
        <h2>Local capability setup</h2>
        <p className="lede">Install and verify the local tools and models Echodraft uses for private audiobook production.</p>
        <div className="model-summary">
          <strong>
            {readyRequired}/{required.length} required ready
          </strong>
          <small>Runtime files and setup logs are stored under the local Echodraft workspace.</small>
        </div>
        {running ? (
          <div className="chapter-progress model-progress" aria-live="polite">
            <div className="chapter-progress-row">
              <span>{installJob?.currentStep || String(job.progress.message ?? "Working")}</span>
              <span>{installJob?.progressPercent ?? progressNumber(job.progress.progressPercent) ?? 0}%</span>
            </div>
            <progress
              className="chapter-progress-bar"
              value={installJob?.progressPercent ?? progressNumber(job.progress.progressPercent) ?? 0}
              max={100}
            />
            <p className="chapter-progress-detail">{activeKey ? `Installing ${activeKey}` : "Local setup is running."}</p>
          </div>
        ) : null}
      </div>
      <div className="studio-card model-grid">
        {ordered.map((item) => (
          <article className={`model-card ${item.health}`} key={item.modelKey}>
            <div className="model-card-heading">
              <div>
                <strong>{item.displayName}</strong>
                <small>
                  {capabilityLabel(item.capability)} · {item.provider}
                </small>
              </div>
              <span className={`model-badge ${item.health}`}>{modelStatus(item)}</span>
            </div>
            <p>{item.description}</p>
            <div className="model-meta">
              <span>{item.installType.replaceAll("_", " ")}</span>
              {item.sizeMb ? <span>{item.sizeMb} MB</span> : null}
              {item.required ? <span>Required</span> : <span>Optional</span>}
            </div>
            {item.licenseSummary ? <small className="license-note">{item.licenseSummary}</small> : null}
            {item.installPath ? <small className="model-path">{item.installPath}</small> : null}
            <div className="model-actions">
              <button type="button" className="small-button" disabled={busy || Boolean(running)} onClick={() => void onInstall(item)}>
                {item.health === "ready" ? "Repair" : "Install"}
              </button>
              <button type="button" className="small-button" disabled={busy || Boolean(running)} onClick={() => void onVerify(item)}>
                Verify
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
