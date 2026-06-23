# Stage 03 — Character registry and casting

## Outcome

Give each narrator and character a stable, reviewable voice assignment before bulk audio generation.

## Implement

- Add `Character`, `VoiceProfile`, `CharacterVoiceAssignment`, and `PronunciationEntry` tables and domain models.
- Implement CRUD APIs and UI panels for characters, aliases, narrative role, notes, confidence, voice profiles, and pronunciation overrides.
- Add a narrator record per project and prevent deletion while segments still depend on it.
- Convert character-candidate output into reviewable proposed characters. Require user confirmation before a candidate becomes an assignment.
- Implement speaker attribution per segment with an explicit `unknown` state and a confidence value. Never treat low-confidence dialogue attribution as certain.
- Store a versioned `manifests/voice_bible.json` containing narrator, characters, selected voice profiles, aliases, pronunciation rules, and approval state.
- Add a casting UI with candidate review, merge/split character actions, assignment controls, unknown-speaker queue, and per-segment speaker overrides.

## Validation

- Test CRUD validation, unique aliases, assignment replacement, pronunciation precedence, and narrator constraints.
- Test that changing a voice assignment marks only affected segment renders stale.
- Use a dialogue fixture to verify that ambiguous speakers remain reviewable rather than incorrectly auto-assigned.

## Done when

A user can map a narrator and several characters to stable voice profiles, correct uncertain attribution, and inspect the generated voice bible.
