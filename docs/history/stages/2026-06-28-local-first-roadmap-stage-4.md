# Local-First Roadmap Stage 4 Implementation Plan

Goal: add book-aware structure parsing, parser warnings/evidence, user locks, split/merge editing, and a Structure Editor UI.

## Scope

- Add parser evidence and lock metadata to chapters, scenes, and segments.
- Add parser warning and structure lock tables.
- Upgrade structure extraction for front matter, chapter/prologue/epilogue/part/book headings, scene headings, dialogue, paragraphs, and performance beats.
- Persist parser warnings with scope, evidence, confidence, and resolved state.
- Add chapter/scene edit APIs, structure lock API, and segment split/merge APIs.
- Surface parser warnings and segment lock/split/merge controls in the dashboard.

## Implementation Notes

- Parser v2 writes `structure_manifest` schema version `0.2.0`.
- Segment locks are carried forward during parser reruns by reattaching locked segment records to the new parsed scene that covers the original offset.
- Split and merge preserve segment revision history for the primary edited segment and mark it `needs_review`.
- Parser warnings are metadata only; canonical text remains clean manuscript text.

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
