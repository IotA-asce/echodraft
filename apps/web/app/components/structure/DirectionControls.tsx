import { useState } from "react";
import type { Direction, Segment, SegmentDirection } from "../../api";

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

export function DirectionControls({
  segment,
  saved,
  onSave,
}: {
  segment: Segment;
  saved?: SegmentDirection;
  onSave: (segmentId: string, direction: Direction) => Promise<void>;
}) {
  const base = saved?.direction ?? directionFor("segment", segment.id);
  const [draft, setDraft] = useState<Direction>(base);
  const update = (patch: Partial<Direction>) => setDraft((current) => ({ ...current, ...patch, scopeType: "segment", scopeId: segment.id }));
  return (
    <div className="direction-studio">
      <div className="source-heading">
        <strong>Direction Studio</strong>
        <span>{saved ? `${saved.source}${saved.userLocked ? " · locked" : ""}` : "default"}</span>
      </div>
      <div className="direction-controls">
        <label>
          Emotion
          <select value={draft.emotion} onChange={(event) => update({ emotion: event.currentTarget.value, tone: event.currentTarget.value })}>
            <option value="neutral">Neutral</option>
            <option value="warm">Warm</option>
            <option value="tense">Tense</option>
            <option value="quiet">Quiet</option>
            <option value="urgent">Urgent</option>
            <option value="somber">Somber</option>
            <option value="bright">Bright</option>
            <option value="fearful">Fearful</option>
            <option value="angry">Angry</option>
          </select>
        </label>
        <label>
          Pace
          <input type="range" min="0.5" max="2" step="0.05" value={draft.pace} onChange={(event) => update({ pace: Number(event.currentTarget.value) })} />
          <small>{draft.pace.toFixed(2)}x</small>
        </label>
        <label>
          Intensity
          <input type="range" min="0" max="1" step="0.05" value={draft.intensity} onChange={(event) => update({ intensity: Number(event.currentTarget.value) })} />
          <small>{Math.round(draft.intensity * 100)}%</small>
        </label>
        <label>
          Pause before
          <input type="number" min="0" max="5000" value={draft.pauseBeforeMs} onChange={(event) => update({ pauseBeforeMs: Number(event.currentTarget.value) })} />
        </label>
        <label>
          Pause after
          <input type="number" min="0" max="5000" value={draft.pauseAfterMs} onChange={(event) => update({ pauseAfterMs: Number(event.currentTarget.value) })} />
        </label>
        <label className="direction-check">
          <input type="checkbox" checked={draft.emphasis} onChange={(event) => update({ emphasis: event.currentTarget.checked })} />
          Emphasis
        </label>
        <label className="direction-check">
          <input type="checkbox" checked={draft.whisper} onChange={(event) => update({ whisper: event.currentTarget.checked })} />
          Whisper
        </label>
      </div>
      <button type="button" className="small-button" onClick={() => void onSave(segment.id, draft)}>
        Save direction
      </button>
    </div>
  );
}
