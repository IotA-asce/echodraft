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

- User locks survive reruns and local extraction passes.
- Merge preserves the source record with `mergedIntoCharacterId`; it does not delete data.
- Split creates a new character and appends history on both records.
- Voice links must reference a voice profile in the same project.
- Automatic speaker attribution and production voice resolution are deferred to later roadmap stages.

## API Surface

- `GET /api/v1/projects/{projectId}/characters`
- `POST /api/v1/projects/{projectId}/characters`
- `PATCH /api/v1/characters/{characterId}`
- `POST /api/v1/characters/{characterId}/merge`
- `POST /api/v1/characters/{characterId}/split`
- `POST /api/v1/characters/{characterId}/assign-voice`

## UI Surface

The dashboard Voice Bible panel supports creating character records, editing canonical names, aliases, traits, and roles, linking a voice, locking records, and issuing merge or split operations.
