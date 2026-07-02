import type { VoiceProfile } from "../../api";

export function VoiceProfileCard({
  voice,
  selected,
  onPreview,
  onSelectNarrator,
  onRemove,
}: {
  voice: VoiceProfile;
  selected: boolean;
  onPreview: (voiceId: string) => void;
  onSelectNarrator: (voiceId: string) => void;
  onRemove: (voiceId: string) => void;
}) {
  return (
    <article className={selected ? "voice-card selected-voice" : "voice-card"}>
      <div>
        <strong>{voice.name}</strong>
        <small>{voice.providerVoiceId}</small>
      </div>
      <span>
        <button type="button" className="small-button" onClick={() => onPreview(voice.id)}>
          Preview
        </button>
        <button type="button" className="small-button" onClick={() => onSelectNarrator(voice.id)}>
          {selected ? "Narrator" : "Set narrator"}
        </button>
        <button type="button" className="small-button" disabled={selected} onClick={() => onRemove(voice.id)}>
          Remove
        </button>
      </span>
    </article>
  );
}
