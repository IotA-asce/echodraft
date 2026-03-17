# Voice Bible Spec

See also: [domain-model.md](domain-model.md), [pipeline-manifest-spec.md](pipeline-manifest-spec.md), [qa-rulebook.md](qa-rulebook.md)

## Purpose
The voice bible is the project-level source of truth for narrator identity, character casting, pronunciation behavior, and moderation rules. It exists to preserve long-form consistency across renders and patch cycles.

## Principles
- Consistency matters more than novelty.
- Voice assignments must be explicit and durable.
- Narrator identity remains stable across the title.
- Character variation must be recognizable but not cartoonish.
- Editorial control beats generative improvisation.

## Voice bible structure
A voice bible contains:
- narrator profile
- character profiles
- pronunciation dictionary
- global style and intensity rules
- do-not-cross rules

## Narrator profile
Required fields:
- `voiceProfileId`
- `name`
- `role`
- `toneKeywords`
- `pacingDefault`
- `energyDefault`
- `warmth`
- `clarity`
- `accentNotes`
- `stylePrompt`
- `doNotOverdo`

Narrator rules:
- one project has at most one active narrator identity
- narrator voice must not drift between chapters without explicit project-level change
- narrator delivery should favor clarity and restraint over theatrics

## Character profile
Required fields:
- `characterId`
- `displayName`
- `aliases`
- `voiceProfileId`
- `characterSummary`
- `vocalIdentity`
- `deliveryDefaults`
- `emotionalRange`
- `accentNotes`
- `speechQuirks`
- `relationshipToNarrator`
- `usageRules`

Character rules:
- major characters should have distinct voices when practical
- supporting voices may be reused for minor roles
- accent or stylization choices must not compromise intelligibility
- character voices should contrast with narrator voice clearly enough for dialogue readability

## Pronunciation dictionary
Fields:
- `term`
- `phonetic`
- `replacementText`
- `appliesToCharacters`
- `notes`

Rules:
- pronunciation overrides apply before render-key generation
- edits invalidate only impacted segments
- special names, invented terms, and high-risk words should be explicit

## Global style and intensity rules
Suggested fields:
- `maxExpressiveness`
- `allowWhispering`
- `allowShouting`
- `pauseStyle`
- `dialogueSeparationGoal`
- `narrationRestraint`

Default guidance:
- `maxExpressiveness`: `medium`
- `allowWhispering`: `true` only when intelligibility remains intact
- `allowShouting`: `false` by default in MVP
- `narrationRestraint`: `high`

## Do-not-cross rules
- Narrator voice must never be assigned to non-narrator characters unless explicitly approved.
- Minor characters may share voices; major characters should not if avoidable.
- Comedic delivery must not break scene tone.
- Ambience and performance intensity must not overpower speech clarity.
- Voice changes after chapter approval require stale-state handling and QA rerun.

## Example shape
```json
{
  "schemaVersion": "0.1.0",
  "projectId": "proj_001",
  "narrator": {
    "voiceProfileId": "voice_narrator_01",
    "name": "Narrator Main"
  },
  "characters": [],
  "pronunciations": [],
  "globalRules": {
    "maxExpressiveness": "medium",
    "allowWhispering": true,
    "allowShouting": false,
    "narrationRestraint": "high"
  }
}
```

## Workflow rules
- Build the voice bible before full chapter generation.
- Narrator changes may invalidate all chapters unless intentionally forked as a new project branch.
- Character voice changes mark affected segment renders as stale.
- Pronunciation edits invalidate only segments containing impacted terms.
- Voice preview should happen before long-running chapter generation whenever possible.
