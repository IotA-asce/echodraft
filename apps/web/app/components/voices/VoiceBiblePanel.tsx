import type { FormEvent } from "react";
import type { Character, Pronunciation, SpeakerAttribution, VoiceProfile, VoiceSuggestion } from "../../api";
import { ReferenceForm } from "../common/ReferenceForm";
import { EmptyState } from "../common/EmptyState";
import { CastReview } from "./CastReview";
import { CharacterBible } from "./CharacterBible";
import { NarratorCard } from "./NarratorCard";
import { VoiceProfileCard } from "./VoiceProfileCard";

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

type SpeakerAttributionUpdatePayload = {
  characterId?: string | null;
  speakerName?: string | null;
  status?: string;
  userLocked?: boolean;
};

export function VoiceBiblePanel({
  voices,
  narrator,
  voiceName,
  providerVoiceId,
  characters,
  attributions,
  pronunciations,
  characterName,
  characterAliases,
  characterTraits,
  busy,
  onVoiceNameChange,
  onProviderVoiceIdChange,
  onAddVoice,
  onPreviewVoice,
  onSelectNarrator,
  onRemoveVoice,
  onCharacterNameChange,
  onCharacterAliasesChange,
  onCharacterTraitsChange,
  onAddCharacter,
  onSaveCharacter,
  onMergeCharacter,
  onSplitCharacter,
  onLoadVoiceSuggestions,
  onPreviewVoiceSuggestion,
  onRunCastReview,
  onSaveAttribution,
  onAddPronunciation,
}: {
  voices: VoiceProfile[];
  narrator: VoiceProfile | null;
  voiceName: string;
  providerVoiceId: string;
  characters: Character[];
  attributions: SpeakerAttribution[];
  pronunciations: Pronunciation[];
  characterName: string;
  characterAliases: string;
  characterTraits: string;
  busy: boolean;
  onVoiceNameChange: (value: string) => void;
  onProviderVoiceIdChange: (value: string) => void;
  onAddVoice: (event: FormEvent) => void;
  onPreviewVoice: (voiceId: string) => void;
  onSelectNarrator: (voiceId: string) => void;
  onRemoveVoice: (voiceId: string) => void;
  onCharacterNameChange: (value: string) => void;
  onCharacterAliasesChange: (value: string) => void;
  onCharacterTraitsChange: (value: string) => void;
  onAddCharacter: (event: FormEvent) => void;
  onSaveCharacter: (characterId: string, payload: CharacterUpdatePayload) => Promise<void>;
  onMergeCharacter: (source: Character, targetId: string) => Promise<void>;
  onSplitCharacter: (character: Character) => Promise<void>;
  onLoadVoiceSuggestions: (characterId: string) => Promise<VoiceSuggestion[]>;
  onPreviewVoiceSuggestion: (voiceId: string, sampleText: string) => void;
  onRunCastReview: (useLocalLlm?: boolean) => Promise<void>;
  onSaveAttribution: (attributionId: string, payload: SpeakerAttributionUpdatePayload) => Promise<void>;
  onAddPronunciation: (value: string) => Promise<void>;
}) {
  return (
    <section className="studio-section voice-bible-panel" aria-labelledby="voice-bible-title">
      <div>
        <p className="eyebrow">04 / Voices & Cast</p>
        <h2 id="voice-bible-title">Voice Bible</h2>
        <p className="lede">Review cast, merge duplicates, assign local voices, and keep narrator fallback explicit.</p>
      </div>
      <div className="studio-card">
        <NarratorCard narrator={narrator} />
        <form className="inline-form" onSubmit={onAddVoice}>
          <input aria-label="Voice profile name" placeholder="Profile name" value={voiceName} onChange={(event) => onVoiceNameChange(event.target.value)} />
          <input aria-label="Local provider voice ID or preset ID" placeholder="Local provider voice ID or preset ID" value={providerVoiceId} onChange={(event) => onProviderVoiceIdChange(event.target.value)} />
          <button>Add voice</button>
        </form>
        {voices.length ? (
          <div className="voice-list">
            {voices.map((voice) => (
              <VoiceProfileCard
                key={voice.id}
                voice={voice}
                selected={narrator?.id === voice.id}
                onPreview={onPreviewVoice}
                onSelectNarrator={onSelectNarrator}
                onRemove={onRemoveVoice}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="No voice profiles yet." description="Add a profile from a local voice engine, or use managed Kokoro presets after setup." />
        )}
        <CharacterBible
          characters={characters}
          voices={voices}
          name={characterName}
          aliases={characterAliases}
          traits={characterTraits}
          onNameChange={onCharacterNameChange}
          onAliasesChange={onCharacterAliasesChange}
          onTraitsChange={onCharacterTraitsChange}
          onAdd={onAddCharacter}
          onSave={onSaveCharacter}
          onMerge={onMergeCharacter}
          onSplit={onSplitCharacter}
          onLoadVoiceSuggestions={onLoadVoiceSuggestions}
          onPreviewVoiceSuggestion={onPreviewVoiceSuggestion}
        />
        <CastReview attributions={attributions} characters={characters} onRun={onRunCastReview} onSave={onSaveAttribution} busy={busy} />
        <div className="reference-grid pronunciation-only">
          <ReferenceForm
            label="Pronunciation reference"
            placeholder="Term / preferred wording"
            items={pronunciations.map((item) => (item.replacementText ? `${item.term} -> ${item.replacementText}` : item.term))}
            onSubmit={onAddPronunciation}
          />
        </div>
      </div>
    </section>
  );
}
