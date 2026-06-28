import type { TtsProvider, TtsProviderInfo } from "../../api";

export function ProviderStatus({ providers, active }: { providers: TtsProviderInfo[]; active: TtsProvider }) {
  return (
    <div className="provider-status-grid">
      {providers.map((item) => (
        <article className={item.provider === active ? "provider-status active" : "provider-status"} key={item.provider}>
          <div>
            <strong>{item.displayName}</strong>
            <small>{item.setupMode || item.provider}</small>
          </div>
          <span className={item.ready ? "model-badge ready" : "model-badge missing"}>{item.ready ? "Ready" : "Setup"}</span>
          {item.message ? <p>{item.message}</p> : <p>{item.availableVoices.length ? `${item.availableVoices.length} local voices` : "No local voices registered"}</p>}
        </article>
      ))}
    </div>
  );
}
