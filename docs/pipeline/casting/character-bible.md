# Character Bible

The Character Bible is the project-level source of truth for cast identity and voice links. It is local-first metadata; it does not rewrite canonical manuscript text.

The cast-graph refactor makes the Character Bible the durable output of a broader cast system:

- a durable character mention ledger stores observed names, aliases, titles, pronouns, and nearby evidence across structure runs;
- shortlist-first dedupe evaluates only the strongest candidate matches before opening duplicate review;
- automated cast graph decisions can confirm high-confidence links and suppress repeated duplicate noise;
- internal character enrichment is additive, so new evidence extends a record without overwriting user edits or canonical source text.

## Stored Data

Each character stores:

- display and canonical names
- aliases and traits. Cast Discovery can fill conservative traits such as `role:captain`, `age:young`, `accent:irish`, or `gender:feminine` only from directly observed names, titles, nearby mentions, and pronoun evidence.
- durable mention-ledger evidence for observed names, aliases, titles, pronouns, and supporting source windows
- optional first-seen source, chapter, and segment references
- role type, confidence, and notes
- user lock state and lock reason
- merge and split history
- additive internal enrichment history for evidence-backed trait or alias updates
- optional voice profile link
- optional merged-into pointer for records that were consolidated

## Editing Rules

- Structure & Cast Draft extracts cast evidence from bounded scene and structure windows instead of treating the full manuscript as one candidate pool.
- The mention ledger is durable across reruns. New extraction passes append evidence and recompute decisions; they do not discard prior confirmed observations.
- Structure & Cast Draft can create high-confidence unique characters automatically from observed dialogue/cast evidence.
- Automated cast graph decisions can resolve high-confidence unique or duplicate outcomes when the shortlist is unambiguous and prior project rulings agree.
- Ambiguous candidates are kept as review issues instead of creating duplicate Character Bible records.
- Same-name candidates are not merged automatically when observed trait namespaces conflict; they become possible-duplicate review issues with match IDs.
- Generated title or nickname aliases are evidence-backed and conservative: new unique records may store them, but matching an existing character through a generated alias requires review.
- Fuzzy spelling variants are routed to possible-duplicate review instead of creating unrelated characters or silently merging.
- Additive internal enrichment can extend aliases, traits, and role notes from new evidence, but it does not overwrite user locks, confirmed names, or canonical text.
- Parser Review can apply evidence-backed cast issues: possible duplicates merge into the selected target, while low-confidence unique candidates are confirmed into the Character Bible.
- User locks survive reruns and local extraction passes.
- Merge preserves the source record with `mergedIntoCharacterId`; it does not delete data.
- Merge also re-points speaker attributions from the merged-away source record to the surviving character.
- Confirmed and rejected merge decisions are remembered per project so future cast discovery respects prior rulings.
- Rejecting a possible duplicate resolves the linked review issue and prevents that pair from being re-flagged.
- Split creates a new character and appends history on both records.
- Voice links must reference a voice profile in the same project.
- Approved speaker attributions use linked character voices during production unless a segment override is set.
- Character voice suggestions rank existing project voice profiles against character traits, including derived Kokoro voice-ID facets such as `gender:feminine`, `accent:american`, and `locale:american`.
- Voice suggestion auditions use an approved representative character line when available, falling back to a neutral audition sentence only when the character has no approved attributed dialogue.

## Pipeline Output

The cast stage emits `casting_manifest.json` as the inspectable handoff for downstream voice and production work. The manifest summarizes:

- Character Bible state after dedupe and automated cast-graph decisions
- unresolved cast review issues that still require human judgment
- narrator and character voice assignments
- pronunciation dictionary version
- cast extraction and attribution diagnostics needed for reruns or review

## API Surface

- `GET /api/v1/projects/{projectId}/characters`
- `POST /api/v1/projects/{projectId}/characters`
- `PATCH /api/v1/characters/{characterId}`
- `POST /api/v1/characters/{characterId}/merge`
- `POST /api/v1/characters/{characterId}/reject-merge`
- `POST /api/v1/characters/{characterId}/split`
- `POST /api/v1/characters/{characterId}/assign-voice`
- `GET /api/v1/characters/{characterId}/voice-suggestions`
- `POST /api/v1/issues/{issueId}/apply-action`
- `GET /api/v1/projects/{projectId}/speaker-attributions`
- `POST /api/v1/projects/{projectId}/speaker-attributions/run`
- `PATCH /api/v1/speaker-attributions/{speakerAttributionId}`

## UI Surface

The dashboard Cast Review & Voice Bible panel supports creating character records, editing canonical names, aliases, traits, and roles, linking a voice, loading ranked voice suggestions, auditioning a suggested voice against the character's own line, locking records, issuing merge or split operations, and reviewing speaker attribution rows in Cast Review. Speaker rows are ordered with unresolved, lowest-confidence items first, and propagated approvals report how many matching rows were updated.

The Structure & Cast Draft Parser Review queue surfaces cast-discovery issues alongside parser warnings. It offers apply, not-a-duplicate, and dismiss actions so evidence-backed character decisions can be completed without leaving the story map.
