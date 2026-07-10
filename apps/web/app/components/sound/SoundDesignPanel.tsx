import type { ChangeEvent } from "react";
import type { SoundAsset, SoundCue } from "../../api";
import { Range, Select } from "../../design-system";
import { formatDuration } from "../../lib/format";

export function SoundDesignPanel({
  assets,
  cues,
  selectedAssetId,
  currentSceneId,
  assetType,
  cueType,
  renderMode,
  gain,
  busy,
  onAssetType,
  onAssetSelect,
  onCueType,
  onRenderMode,
  onGain,
  onFile,
  onAddCue,
  onAssemble,
}: {
  assets: SoundAsset[];
  cues: SoundCue[];
  selectedAssetId: string;
  currentSceneId: string | null;
  assetType: "ambience" | "music" | "sfx";
  cueType: "ambience" | "music" | "sfx";
  renderMode: "light" | "dramatized" | "all";
  gain: number;
  busy: boolean;
  onAssetType: (value: "ambience" | "music" | "sfx") => void;
  onAssetSelect: (value: string) => void;
  onCueType: (value: "ambience" | "music" | "sfx") => void;
  onRenderMode: (value: "light" | "dramatized" | "all") => void;
  onGain: (value: number) => void;
  onFile: (event: ChangeEvent<HTMLInputElement>) => void;
  onAddCue: () => Promise<void>;
  onAssemble: (mode: "clean" | "light" | "dramatized") => Promise<void>;
}) {
  const selected = assets.find((item) => item.id === selectedAssetId) ?? assets[0] ?? null;
  return (
    <div className="sound-design-panel">
      <div className="source-heading">
        <strong>Sound Design</strong>
        <span>{cues.length} cues · clean by default</span>
      </div>
      <div className="sound-design-grid">
        <Select label="Import type" value={assetType} onValueChange={(value) => onAssetType(value as "ambience" | "music" | "sfx")} options={[{ value: "ambience", label: "Ambience" }, { value: "music", label: "Music" }, { value: "sfx", label: "SFX" }]} />
        <label className="sound-upload">
          WAV asset
          <input type="file" accept=".wav,audio/wav,audio/x-wav" disabled={busy} onChange={onFile} />
        </label>
        <Select label="Asset" value={selected?.id ?? ""} onValueChange={onAssetSelect} options={[{ value: "", label: "No asset" }, ...assets.map((asset) => ({ value: asset.id, label: `${asset.name} · ${asset.assetType}` }))]} />
        <Select label="Cue type" value={cueType} onValueChange={(value) => onCueType(value as "ambience" | "music" | "sfx")} options={[{ value: "ambience", label: "Ambience" }, { value: "music", label: "Music" }, { value: "sfx", label: "SFX" }]} />
        <Select label="Mix mode" value={renderMode} onValueChange={(value) => onRenderMode(value as "light" | "dramatized" | "all")} options={[{ value: "light", label: "Light" }, { value: "dramatized", label: "Dramatized" }, { value: "all", label: "Both" }]} />
        <Range label="Gain" min={-48} max={-6} step={1} value={gain} onValueChange={onGain} formatValue={(value) => `${value} dB`} />
      </div>
      <div className="sound-actions">
        <button type="button" className="small-button" disabled={busy || !currentSceneId || !selected} onClick={() => void onAddCue()}>
          Assign to current scene
        </button>
        <button type="button" className="small-button secondary" disabled={busy} onClick={() => void onAssemble("clean")}>
          Assemble clean
        </button>
        <button type="button" className="small-button" disabled={busy} onClick={() => void onAssemble("light")}>
          Assemble light
        </button>
        <button type="button" className="small-button" disabled={busy} onClick={() => void onAssemble("dramatized")}>
          Assemble dramatized
        </button>
      </div>
      {assets.length ? (
        <div className="sound-asset-list">
          {assets.slice(0, 4).map((asset) => (
            <article key={asset.id}>
              <strong>{asset.name}</strong>
              <small>
                {asset.assetType} · {formatDuration(asset.durationMs)}
                {asset.audioUrl ? " · playable" : ""}
              </small>
            </article>
          ))}
        </div>
      ) : (
        <p className="import-placeholder">Import local WAV ambience, music, or SFX to build optional chapter mixes.</p>
      )}
    </div>
  );
}
