import { useState, type FormEvent } from "react";
import type { Character, VoiceProfile, VoiceSuggestion } from "../../api";
import { Select } from "../../design-system";

type CharacterUpdatePayload = Partial<
  Pick<
    Character,
    | "displayName"
    | "canonicalName"
    | "aliases"
    | "traits"
    | "roleType"
    | "confidence"
    | "notes"
    | "userLocked"
    | "lockReason"
    | "voiceProfileId"
  >
>;

function csvList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CharacterBible({
  characters,
  voices,
  name,
  aliases,
  traits,
  onNameChange,
  onAliasesChange,
  onTraitsChange,
  onAdd,
  onSave,
  onMerge,
  onSplit,
  onLoadVoiceSuggestions,
  onPreviewVoiceSuggestion,
}: {
  characters: Character[];
  voices: VoiceProfile[];
  name: string;
  aliases: string;
  traits: string;
  onNameChange: (value: string) => void;
  onAliasesChange: (value: string) => void;
  onTraitsChange: (value: string) => void;
  onAdd: (event: FormEvent) => void;
  onSave: (characterId: string, payload: CharacterUpdatePayload) => Promise<void>;
  onMerge: (source: Character, targetId: string) => Promise<void>;
  onSplit: (character: Character) => Promise<void>;
  onLoadVoiceSuggestions: (characterId: string) => Promise<VoiceSuggestion[]>;
  onPreviewVoiceSuggestion: (voiceId: string, sampleText: string) => void;
}) {
  const [suggestionsByCharacter, setSuggestionsByCharacter] = useState<Record<string, VoiceSuggestion[]>>({});
  const [loadingSuggestionsFor, setLoadingSuggestionsFor] = useState<string | null>(null);
  const activeCharacters = characters.filter((item) => !item.mergedIntoCharacterId);

  async function loadSuggestions(characterId: string) {
    setLoadingSuggestionsFor(characterId);
    try {
      const suggestions = await onLoadVoiceSuggestions(characterId);
      setSuggestionsByCharacter((current) => ({ ...current, [characterId]: suggestions.slice(0, 3) }));
    } finally {
      setLoadingSuggestionsFor(null);
    }
  }

  return (
    <div className="character-bible">
      <div className="source-heading">
        <strong>Character Bible</strong>
        <span>
          {activeCharacters.length} active · {characters.length - activeCharacters.length} merged
        </span>
      </div>
      <form className="character-create" onSubmit={onAdd}>
        <input placeholder="Character name" value={name} onChange={(event) => onNameChange(event.target.value)} />
        <input placeholder="Aliases, comma separated" value={aliases} onChange={(event) => onAliasesChange(event.target.value)} />
        <input placeholder="Traits, comma separated" value={traits} onChange={(event) => onTraitsChange(event.target.value)} />
        <button>Add character</button>
      </form>
      <div className="character-grid">
        {characters.map((character) => {
          const merged = Boolean(character.mergedIntoCharacterId);
          return (
            <article className={merged ? "character-card merged" : "character-card"} key={character.id}>
              <div className="character-heading">
                <div>
                  <strong>{character.displayName}</strong>
                  <small>
                    {character.canonicalName || "No canonical name"} · {Math.round(character.confidence * 100)}%
                  </small>
                </div>
                <span className={character.userLocked ? "character-badge locked" : "character-badge"}>
                  {merged ? "merged" : character.userLocked ? "locked" : character.roleType}
                </span>
              </div>
              <div className="character-fields">
                <label>
                  Display
                  <input
                    disabled={merged}
                    defaultValue={character.displayName}
                    onBlur={(event) => {
                      const value = event.currentTarget.value.trim();
                      if (value && value !== character.displayName) void onSave(character.id, { displayName: value });
                    }}
                  />
                </label>
                <label>
                  Canonical
                  <input
                    disabled={merged}
                    defaultValue={character.canonicalName ?? ""}
                    onBlur={(event) => {
                      const value = event.currentTarget.value.trim();
                      if (value !== (character.canonicalName ?? "")) void onSave(character.id, { canonicalName: value });
                    }}
                  />
                </label>
                <label>
                  Aliases
                  <input
                    disabled={merged}
                    defaultValue={character.aliases.join(", ")}
                    onBlur={(event) => {
                      const value = csvList(event.currentTarget.value);
                      if (value.join("|") !== character.aliases.join("|")) void onSave(character.id, { aliases: value });
                    }}
                  />
                </label>
                <label>
                  Traits
                  <input
                    disabled={merged}
                    defaultValue={character.traits.join(", ")}
                    onBlur={(event) => {
                      const value = csvList(event.currentTarget.value);
                      if (value.join("|") !== character.traits.join("|")) void onSave(character.id, { traits: value });
                    }}
                  />
                </label>
                <Select disabled={merged} label="Role" value={character.roleType} onValueChange={(value) => void onSave(character.id, { roleType: value })} options={[{ value: "major", label: "Major" }, { value: "supporting", label: "Supporting" }, { value: "minor", label: "Minor" }, { value: "narrator", label: "Narrator" }]} />
                <Select disabled={merged} label="Voice" value={character.voiceProfileId ?? ""} onValueChange={(value) => void onSave(character.id, { voiceProfileId: value || null })} options={[{ value: "", label: "No voice link" }, ...voices.map((voice) => ({ value: voice.id, label: voice.name }))]} />
              </div>
              <div className="character-actions">
                <button
                  type="button"
                  className="small-button"
                  disabled={merged}
                  onClick={() =>
                    void onSave(character.id, {
                      userLocked: !character.userLocked,
                      lockReason: character.userLocked ? null : "Locked in Character Bible",
                    })
                  }
                >
                  {character.userLocked ? "Unlock" : "Lock"}
                </button>
                <button type="button" className="small-button" disabled={merged} onClick={() => void onSplit(character)}>
                  Split
                </button>
                <Select disabled={merged} label={`Merge ${character.displayName}`} value="" onValueChange={(value) => value && void onMerge(character, value)} options={[{ value: "", label: "Merge into…" }, ...activeCharacters.filter((target) => target.id !== character.id).map((target) => ({ value: target.id, label: target.displayName }))]} />
              </div>
              {!merged ? (
                <div className="voice-suggestion-panel" aria-label={`Suggestions for ${character.displayName}`}>
                  <div className="voice-suggestion-heading">
                    <strong>Voice suggestions</strong>
                    <button type="button" className="small-button" disabled={loadingSuggestionsFor === character.id} onClick={() => void loadSuggestions(character.id)}>
                      {loadingSuggestionsFor === character.id ? "Loading..." : "Suggest voices"}
                    </button>
                  </div>
                  {(suggestionsByCharacter[character.id] ?? []).length ? (
                    <div className="voice-suggestion-list">
                      {(suggestionsByCharacter[character.id] ?? []).map((suggestion) => (
                        <article key={suggestion.voiceProfileId} className="voice-suggestion-card">
                          <div>
                            <strong>{suggestion.name}</strong>
                            <small>
                              {Math.round(suggestion.score * 100)}% match
                              {suggestion.matchedTraits.length ? ` · ${suggestion.matchedTraits.join(", ")}` : ""}
                            </small>
                            <p>{suggestion.sampleText}</p>
                            {suggestion.facets?.length ? <small>{suggestion.facets.join(" · ")}</small> : null}
                          </div>
                          <span>
                            <button type="button" className="small-button" onClick={() => onPreviewVoiceSuggestion(suggestion.voiceProfileId, suggestion.sampleText)}>
                              Audition
                            </button>
                            <button type="button" className="small-button" onClick={() => void onSave(character.id, { voiceProfileId: suggestion.voiceProfileId })}>
                              Assign
                            </button>
                          </span>
                        </article>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {character.mergeHistory.length || character.splitHistory.length || character.lockReason ? (
                <p className="character-history">
                  {character.lockReason ? `${character.lockReason} · ` : ""}
                  {character.mergeHistory.length} merges · {character.splitHistory.length} splits
                </p>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
