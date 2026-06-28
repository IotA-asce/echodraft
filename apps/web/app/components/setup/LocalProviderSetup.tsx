import type { Dispatch, SetStateAction } from "react";
import type { TtsProvider, TtsSettings } from "../../api";

const emptyTts = (provider: TtsProvider): TtsSettings => ({
  provider,
  setupMode: provider === "kokoro" ? "managed_onnx" : provider === "piper" ? "local_cli" : provider === "xtts_v2" ? "coqui_local" : null,
  ready: false,
  availableVoices: [],
  referenceVoiceConsent: false,
  language: "en",
});

export function LocalProviderSetup({
  provider,
  tts,
  onChange,
  onSave,
  busy,
}: {
  provider: TtsProvider;
  tts: TtsSettings;
  onChange: Dispatch<SetStateAction<TtsSettings | null>>;
  onSave: () => Promise<void>;
  busy: boolean;
}) {
  if (provider === "piper") {
    return (
      <div className="advanced-tts provider-setup">
        <p className="capability">Piper fallback uses a local Piper CLI and ONNX voice model. Multi-speaker IDs can be entered as voice IDs such as speaker:0.</p>
        <label>
          Executable
          <input value={tts.executable ?? ""} placeholder="piper" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("piper")), provider: "piper", setupMode: "local_cli", executable: event.target.value }))} />
        </label>
        <label>
          Piper model
          <input value={tts.piperModelPath ?? ""} placeholder="/path/to/voice.onnx" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("piper")), provider: "piper", setupMode: "local_cli", piperModelPath: event.target.value }))} />
        </label>
        <label>
          Piper config
          <input value={tts.piperConfigPath ?? ""} placeholder="/path/to/voice.onnx.json" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("piper")), provider: "piper", setupMode: "local_cli", piperConfigPath: event.target.value }))} />
        </label>
        <label>
          Voice registry
          <input value={tts.voiceRegistryPath ?? ""} placeholder="Optional text file of voice IDs" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("piper")), provider: "piper", setupMode: "local_cli", voiceRegistryPath: event.target.value }))} />
        </label>
        <button type="button" onClick={() => void onSave()} disabled={busy}>
          Save Piper fallback
        </button>
      </div>
    );
  }
  return (
    <div className="advanced-tts provider-setup">
      <p className="capability">XTTS-v2 is opt-in. Use only a local reference voice you have rights and consent to use.</p>
      <label>
        Python runtime
        <input value={tts.pythonPath ?? ""} placeholder="/path/to/python" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("xtts_v2")), provider: "xtts_v2", setupMode: "coqui_local", pythonPath: event.target.value }))} />
      </label>
      <label>
        Reference voice WAV
        <input value={tts.referenceVoicePath ?? ""} placeholder="/path/to/reference.wav" onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("xtts_v2")), provider: "xtts_v2", setupMode: "coqui_local", referenceVoicePath: event.target.value }))} />
      </label>
      <label>
        Language
        <input value={tts.language || "en"} onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("xtts_v2")), provider: "xtts_v2", setupMode: "coqui_local", language: event.target.value || "en" }))} />
      </label>
      <label className="direction-check">
        <input type="checkbox" checked={tts.referenceVoiceConsent} onChange={(event) => onChange((current) => ({ ...(current ?? emptyTts("xtts_v2")), provider: "xtts_v2", setupMode: "coqui_local", referenceVoiceConsent: event.currentTarget.checked }))} />I have consent to use this local reference voice.
      </label>
      <button type="button" onClick={() => void onSave()} disabled={busy || !tts.referenceVoiceConsent}>
        Save XTTS-v2
      </button>
    </div>
  );
}
