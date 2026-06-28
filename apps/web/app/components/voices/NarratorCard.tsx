import type { VoiceProfile } from "../../api";

export function NarratorCard({ narrator }: { narrator: VoiceProfile | null }) {
  return (
    <article className={narrator ? "narrator-card ready" : "narrator-card"}>
      <div>
        <p className="eyebrow">Narrator</p>
        <strong>{narrator?.name ?? "No narrator selected"}</strong>
        <small>{narrator ? `${narrator.backend} · ${narrator.providerVoiceId}` : "Choose a voice profile before producing chapter audio."}</small>
      </div>
    </article>
  );
}
