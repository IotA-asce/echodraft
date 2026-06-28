# Stage 12: Review & Patch Workbench

Branch: `codex/stage-12-review-patch-workbench`

## Implemented Scope

- Added `SegmentReviewInspector` and `PatchAttempt` domain contracts.
- Added a backend review workbench read model that aggregates segment source/canonical text, structure evidence, parser warnings, cast attribution, saved direction, render history, waveform metadata, QA issues, comments, and patch attempts.
- Added `GET /api/v1/projects/{projectId}/segments/{segmentId}/review-inspector`.
- Upgraded the dashboard segment action from compare-only to `Inspect`, loading both render comparison and the layered inspector.
- Added a Review & Patch Workbench panel for source, canonical, structure, cast, direction, waveform, render history, QA, comments, and patch queue layers.
- Added regression coverage for inspector layers, patch queue lineage, waveform metadata, and selective stale-render behavior.

## Architecture Notes

- No new database table was needed. Stage 12 reads existing structure, speaker, direction, render, issue, comment, and patch attempt tables.
- Segment audio and waveform details remain artifact-backed. The inspector reads render metadata JSON and returns artifact URLs for audio.
- Patch attempts remain append-only and continue to point at old/new segment render IDs plus the owning chapter render ID.
- Segment text edits still use segment revisions and render fingerprints, so only the edited segment becomes stale.

## Validation Plan

- `uv run pytest`
- `uv run ruff check .`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src`
- `npm run web:typecheck`
- `npm run web:lint`
- `npm run web:test:smoke` when the existing local API port conflict is cleared
