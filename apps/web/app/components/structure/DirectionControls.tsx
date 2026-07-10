import { useState } from "react";
import type { Direction, Segment, SegmentDirection } from "../../api";
import { Range, Select } from "../../design-system";

const directionFor = (scopeType: string, scopeId: string): Direction => ({
  scopeType,
  scopeId,
  pace: 1,
  intensity: 0.4,
  tone: "neutral",
  emotion: "neutral",
  pauseBeforeMs: 0,
  pauseAfterMs: 120,
  stylePrompt: "Clear, restrained audiobook narration",
  emphasis: false,
  whisper: false,
  noSfx: true,
});

const NOT_HONORED_HINT = "not honored by current engine";

export function DirectionControls({
  segment,
  saved,
  supportedDirection,
  onSave,
}: {
  segment: Segment;
  saved?: SegmentDirection;
  supportedDirection?: string[] | null;
  onSave: (segmentId: string, direction: Direction) => Promise<void>;
}) {
  const base = saved?.direction ?? directionFor("segment", segment.id);
  const [draft, setDraft] = useState<Direction>(base);
  const update = (patch: Partial<Direction>) => setDraft((current) => ({ ...current, ...patch, scopeType: "segment", scopeId: segment.id }));
  // A null/undefined capability list means "engine unknown": don't annotate anything,
  // since renders can switch engine later and disabling would be too strong.
  const honored = supportedDirection ?? null;
  const unsupported = (control: string) => (honored ? !honored.includes(control) : false);
  const hint = (control: string) => (unsupported(control) ? <em className="direction-unhonored"> · {NOT_HONORED_HINT}</em> : null);
  const pausesHonored = honored ? honored.includes("pauseBeforeMs") || honored.includes("pauseAfterMs") : true;
  const pauseHint = !pausesHonored ? <em className="direction-unhonored"> · {NOT_HONORED_HINT}</em> : null;
  return (
    <div className="direction-studio">
      <div className="source-heading">
        <strong>Direction Studio</strong>
        <span>{saved ? `${saved.source}${saved.userLocked ? " · locked" : ""}` : "default"}</span>
      </div>
      <div className="direction-controls">
        <Select className={unsupported("emotion") ? "direction-unsupported" : undefined} label={`Emotion${unsupported("emotion") ? ` · ${NOT_HONORED_HINT}` : ""}`} value={draft.emotion} onValueChange={(value) => update({ emotion: value, tone: value })} options={["neutral", "warm", "tense", "quiet", "urgent", "somber", "bright", "fearful", "angry"].map((value) => ({ value, label: value[0].toUpperCase() + value.slice(1) }))} />
        <Range className={unsupported("pace") ? "direction-unsupported" : undefined} label={`Pace${unsupported("pace") ? ` · ${NOT_HONORED_HINT}` : ""}`} min={0.5} max={2} step={0.05} value={draft.pace} onValueChange={(value) => update({ pace: value })} formatValue={(value) => `${value.toFixed(2)}x`} />
        <Range className={unsupported("intensity") ? "direction-unsupported" : undefined} label={`Intensity${unsupported("intensity") ? ` · ${NOT_HONORED_HINT}` : ""}`} min={0} max={1} step={0.05} value={draft.intensity} onValueChange={(value) => update({ intensity: value })} formatValue={(value) => `${Math.round(value * 100)}%`} />
        <label className={!pausesHonored ? "direction-unsupported" : undefined}>
          Pause before{pauseHint}
          <input type="number" min="0" max="5000" value={draft.pauseBeforeMs} onChange={(event) => update({ pauseBeforeMs: Number(event.currentTarget.value) })} />
        </label>
        <label className={!pausesHonored ? "direction-unsupported" : undefined}>
          Pause after{pauseHint}
          <input type="number" min="0" max="5000" value={draft.pauseAfterMs} onChange={(event) => update({ pauseAfterMs: Number(event.currentTarget.value) })} />
        </label>
        <label className={unsupported("emphasis") ? "direction-check direction-unsupported" : "direction-check"}>
          <input type="checkbox" checked={draft.emphasis} onChange={(event) => update({ emphasis: event.currentTarget.checked })} />
          Emphasis{hint("emphasis")}
        </label>
        <label className={unsupported("whisper") ? "direction-check direction-unsupported" : "direction-check"}>
          <input type="checkbox" checked={draft.whisper} onChange={(event) => update({ whisper: event.currentTarget.checked })} />
          Whisper{hint("whisper")}
        </label>
      </div>
      <button type="button" className="small-button" onClick={() => void onSave(segment.id, draft)}>
        Save direction
      </button>
    </div>
  );
}
