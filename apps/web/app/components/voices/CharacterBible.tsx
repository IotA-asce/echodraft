import type { FormEvent } from "react";
import type { Character, VoiceProfile } from "../../api";

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
}) {
  const activeCharacters = characters.filter((item) => !item.mergedIntoCharacterId);
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
                <label>
                  Role
                  <select disabled={merged} value={character.roleType} onChange={(event) => void onSave(character.id, { roleType: event.currentTarget.value })}>
                    <option value="major">Major</option>
                    <option value="supporting">Supporting</option>
                    <option value="minor">Minor</option>
                    <option value="narrator">Narrator</option>
                  </select>
                </label>
                <label>
                  Voice
                  <select disabled={merged} value={character.voiceProfileId ?? ""} onChange={(event) => void onSave(character.id, { voiceProfileId: event.currentTarget.value || null })}>
                    <option value="">No voice link</option>
                    {voices.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.name}
                      </option>
                    ))}
                  </select>
                </label>
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
                <select disabled={merged} value="" aria-label={`Merge ${character.displayName}`} onChange={(event) => void onMerge(character, event.currentTarget.value)}>
                  <option value="">Merge into...</option>
                  {activeCharacters
                    .filter((target) => target.id !== character.id)
                    .map((target) => (
                      <option key={target.id} value={target.id}>
                        {target.displayName}
                      </option>
                    ))}
                </select>
              </div>
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
