# Local-First Roadmap Stage 6 Implementation Plan

Goal: expand character records into an editable Character Bible.

## Scope

- Add Character Bible fields for canonical names, aliases, traits, first-seen references, locks, history, and voice links.
- Add migration and local SQLite drift repair for existing alpha databases.
- Add update, merge, and split character APIs.
- Preserve merged source records for traceability.
- Add dashboard controls for editing cast metadata, assigning voices, locking records, and merge/split operations.
- Document the Character Bible data contract and current production boundary.

## Implementation Notes

- Character metadata stays outside canonical manuscript text.
- Merge appends history to the target and marks the source as merged into the target.
- Split appends history to both the original and new character.
- Voice assignment validates that the voice profile belongs to the same project.
- Production voice resolution from attributed speakers is deferred to the speaker attribution stage.

## Validation

Run:

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/db/src libs/domain-models/src
npm run web:typecheck
npm run web:lint
```

Expected result: all checks pass.
