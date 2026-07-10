import { memo, useMemo, useRef, useState, type FormEvent } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeCharacters = useMemo(
    () => characters.filter((item) => !item.mergedIntoCharacterId),
    [characters],
  );
  // TanStack Virtual intentionally owns mutable scroll state; React Compiler skips this component.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: characters.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 260,
    getItemKey: (index) => characters[index]?.id ?? index,
    overscan: 6,
    useFlushSync: false,
  });

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
      <div ref={scrollRef} className="character-grid virtual-scroll" data-testid="virtual-character-grid">
        <div className="virtual-list-canvas" style={{ height: `${virtualizer.getTotalSize()}px` }}>
          {virtualizer.getVirtualItems().map((row) => {
            const character = characters[row.index];
            if (!character) return null;
            return (
              <div key={row.key} data-index={row.index} ref={virtualizer.measureElement} className="virtual-list-row" style={{ transform: `translateY(${row.start}px)` }}>
                <CharacterBibleRow
                  character={character}
                  voices={voices}
                  activeCharacters={activeCharacters}
                  onSave={onSave}
                  onMerge={onMerge}
                  onSplit={onSplit}
                  onLoadVoiceSuggestions={onLoadVoiceSuggestions}
                  onPreviewVoiceSuggestion={onPreviewVoiceSuggestion}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Memoized row: the only reactive identity that changes per-keystroke is
// this row's own local suggestion-loading state (owned here, not lifted to
// CharacterBible), so unrelated rows and unrelated top-level state changes
// elsewhere in ProjectDashboard never re-render a row that isn't involved.
// See docs/ui/frontend-architecture.md ("Row component design").
const CharacterBibleRow = memo(function CharacterBibleRow({
  character,
  voices,
  activeCharacters,
  onSave,
  onMerge,
  onSplit,
  onLoadVoiceSuggestions,
  onPreviewVoiceSuggestion,
}: {
  character: Character;
  voices: VoiceProfile[];
  activeCharacters: Character[];
  onSave: (characterId: string, payload: CharacterUpdatePayload) => Promise<void>;
  onMerge: (source: Character, targetId: string) => Promise<void>;
  onSplit: (character: Character) => Promise<void>;
  onLoadVoiceSuggestions: (characterId: string) => Promise<VoiceSuggestion[]>;
  onPreviewVoiceSuggestion: (voiceId: string, sampleText: string) => void;
}) {
  const [suggestions, setSuggestions] = useState<VoiceSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const merged = Boolean(character.mergedIntoCharacterId);
  const mergeTargets = useMemo(
    () => activeCharacters.filter((target) => target.id !== character.id),
    [activeCharacters, character.id],
  );

  async function loadSuggestions() {
    setLoadingSuggestions(true);
    try {
      const next = await onLoadVoiceSuggestions(character.id);
      setSuggestions(next.slice(0, 3));
    } finally {
      setLoadingSuggestions(false);
    }
  }

  return (
    <article className={merged ? "character-card merged" : "character-card"}>
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
        <Select disabled={merged} label={`Merge ${character.displayName}`} value="" onValueChange={(value) => value && void onMerge(character, value)} options={[{ value: "", label: "Merge into…" }, ...mergeTargets.map((target) => ({ value: target.id, label: target.displayName }))]} />
      </div>
      {!merged ? (
        <div className="voice-suggestion-panel" aria-label={`Suggestions for ${character.displayName}`}>
          <div className="voice-suggestion-heading">
            <strong>Voice suggestions</strong>
            <button type="button" className="small-button" disabled={loadingSuggestions} onClick={() => void loadSuggestions()}>
              {loadingSuggestions ? "Loading..." : "Suggest voices"}
            </button>
          </div>
          {suggestions.length ? (
            <div className="voice-suggestion-list">
              {suggestions.map((suggestion) => (
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
});
