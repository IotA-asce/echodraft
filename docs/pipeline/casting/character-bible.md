# Character Bible

The Character Bible is the project-level source of truth for cast identity and voice links. It is local-first metadata; it does not rewrite canonical manuscript text.

## Stored Data

Each character stores:

- display and canonical names
- aliases and traits
- optional first-seen source, chapter, and segment references
- role type, confidence, and notes
- user lock state and lock reason
- merge and split history
- optional voice profile link
- optional merged-into pointer for records that were consolidated

## Editing Rules

- Structure & Cast Draft can create high-confidence unique characters automatically from observed dialogue/cast evidence.
- Ambiguous candidates are kept as review issues instead of creating duplicate Character Bible records.
- User locks survive reruns and local extraction passes.
- Merge preserves the source record with `mergedIntoCharacterId`; it does not delete data.
- Merge also re-points speaker attributions from the merged-away source record to the surviving character.
- Confirmed and rejected merge decisions are remembered per project so future cast discovery respects prior rulings.
- Rejecting a possible duplicate resolves the linked review issue and prevents that pair from being re-flagged.
- Split creates a new character and appends history on both records.
- Voice links must reference a voice profile in the same project.
- Approved speaker attributions use linked character voices during production unless a segment override is set.

## API Surface

- `GET /api/v1/projects/{projectId}/characters`
- `POST /api/v1/projects/{projectId}/characters`
- `PATCH /api/v1/characters/{characterId}`
- `POST /api/v1/characters/{characterId}/merge`
- `POST /api/v1/characters/{characterId}/reject-merge`
- `POST /api/v1/characters/{characterId}/split`
- `POST /api/v1/characters/{characterId}/assign-voice`
- `GET /api/v1/projects/{projectId}/speaker-attributions`
- `POST /api/v1/projects/{projectId}/speaker-attributions/run`
- `PATCH /api/v1/speaker-attributions/{speakerAttributionId}`

## UI Surface

The dashboard Cast Review & Voice Bible panel supports creating character records, editing canonical names, aliases, traits, and roles, linking a voice, locking records, issuing merge or split operations, and reviewing speaker attribution rows in Cast Review.
