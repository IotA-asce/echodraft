import type { TtsProvider, TtsProviderInfo } from "../../api";

const CONTROL_LABELS: Record<string, string> = {
  pace: "pace",
  intensity: "intensity",
  tone: "tone",
  emotion: "emotion",
  pauseBeforeMs: "pauses",
  pauseAfterMs: "pauses",
  emphasis: "emphasis",
  whisper: "whisper",
  stylePrompt: "style prompt",
  noSfx: "clean narration",
};

export function honoredDirectionControls(capabilities: Record<string, unknown>): string[] {
  const direction = (capabilities as { direction?: unknown }).direction;
  if (!Array.isArray(direction)) return [];
  const labels: string[] = [];
  for (const control of direction) {
    const label = CONTROL_LABELS[String(control)] ?? String(control);
    if (!labels.includes(label)) labels.push(label);
  }
  return labels;
}

export function ProviderStatus({ providers, active }: { providers: TtsProviderInfo[]; active: TtsProvider }) {
  return (
    <div className="provider-status-grid">
      {providers.map((item) => {
        const honored = honoredDirectionControls(item.capabilities);
        return (
          <article className={item.provider === active ? "provider-status active" : "provider-status"} key={item.provider}>
            <div>
              <strong>{item.displayName}</strong>
              <small>{item.setupMode || item.provider}</small>
            </div>
            <span className={item.ready ? "model-badge ready" : "model-badge missing"}>{item.ready ? "Ready" : "Setup"}</span>
            {item.message ? <p>{item.message}</p> : <p>{item.availableVoices.length ? `${item.availableVoices.length} local voices` : "No local voices registered"}</p>}
            <p className="provider-direction">Honors direction: {honored.length ? honored.join(", ") : "none"}</p>
          </article>
        );
      })}
    </div>
  );
}
