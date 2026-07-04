import type { Character, SpeakerAttribution } from "../../api";

type SpeakerAttributionUpdatePayload = {
  characterId?: string | null;
  speakerName?: string | null;
  status?: string;
  userLocked?: boolean;
};

export function CastReview({
  attributions,
  characters,
  onRun,
  onSave,
  busy,
}: {
  attributions: SpeakerAttribution[];
  characters: Character[];
  onRun: (useLocalLlm?: boolean) => Promise<void>;
  onSave: (attributionId: string, payload: SpeakerAttributionUpdatePayload) => Promise<void>;
  busy: boolean;
}) {
  const activeCharacters = characters.filter((item) => !item.mergedIntoCharacterId);
  const open = attributions.filter((item) => item.status !== "approved");
  const approved = attributions.filter((item) => item.status === "approved");
  const orderedAttributions = [...attributions].sort((left, right) => {
    if (left.status === "approved" && right.status !== "approved") return 1;
    if (left.status !== "approved" && right.status === "approved") return -1;
    return left.confidence - right.confidence;
  });
  const narratorFallback = approved.filter((item) => !item.characterId || !item.voiceProfileId).length;
  return (
    <div className="cast-review">
      <div className="source-heading">
        <strong>Cast Review</strong>
        <span>
          {activeCharacters.length} detected · {approved.length} approved · {open.length} review · {narratorFallback} narrator fallback
          {open.length ? " · lowest confidence first" : ""}
        </span>
      </div>
      <div className="cast-actions">
        <button type="button" className="small-button" disabled={busy} onClick={() => void onRun(false)}>
          Refresh speaker rows
        </button>
        <button type="button" className="small-button" disabled={busy} onClick={() => void onRun(true)}>
          Use local Ollama speaker assist
        </button>
      </div>
      {attributions.length ? (
        <div className="cast-grid">
          {orderedAttributions.map((item) => {
            const preview = typeof item.evidence.textPreview === "string" ? item.evidence.textPreview : "No preview available.";
            return (
              <article className={item.status === "approved" ? "cast-card approved" : "cast-card review"} key={item.id}>
                <div>
                  <b>{item.status.replaceAll("_", " ")}</b>
                  <strong>{item.speakerName || "Unknown speaker"}</strong>
                  <p>{preview}</p>
                  <small>
                    {item.method} · {Math.round(item.confidence * 100)}% confidence{item.characterId ? " · character linked" : " · narrator fallback"}
                    {item.voiceProfileId ? " · voice linked" : ""}
                    {item.userLocked ? " · locked" : ""}
                  </small>
                </div>
                <div className="cast-card-actions">
                  <select
                    value={item.characterId ?? ""}
                    onChange={(event) =>
                      void onSave(item.id, {
                        characterId: event.currentTarget.value || null,
                        status: event.currentTarget.value ? "approved" : "needs_review",
                        userLocked: true,
                      })
                    }
                  >
                    <option value="">No character</option>
                    {activeCharacters.map((character) => (
                      <option key={character.id} value={character.id}>
                        {character.displayName}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="small-button" onClick={() => void onSave(item.id, { characterId: null, status: "approved", userLocked: true })}>
                    Narrator
                  </button>
                  <button type="button" className="small-button" onClick={() => void onSave(item.id, { status: "needs_review", userLocked: !item.userLocked })}>
                    {item.userLocked ? "Unlock" : "Lock"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="import-placeholder">Extract Structure to create the first cast and speaker draft.</p>
      )}
    </div>
  );
}
