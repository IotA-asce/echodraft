# Local-First Roadmap Stage 3 Implementation Plan

Goal: add deterministic cleaning and canonicalization review before structure extraction.

## Scope

- Add cleaning run and text cleanliness issue tables.
- Run deterministic cleaning after source extraction and before canonical normalization.
- Remove page markers, repeated running headers/footers, simple hyphenation breaks, and broken line wraps from canonical text.
- Flag suspicious OCR-like tokens without mutating them automatically.
- Persist a cleaning manifest under the source artifact tree.
- Expose source-by-id preview, cleaning run, and cleaning issue list/update APIs.
- Add Clean Text Review to the dashboard import flow.

## Implementation Notes

- Applied deterministic changes are represented as review records with status `applied`.
- Suspicious tokens are represented as open review records until a user marks them reviewed or resolved.
- Numeric chapter markers are preserved unless they are explicit page markers such as `Page 9` or `[9]`.
- Cleaning issues are metadata. Canonical manuscript text remains clean prose and does not embed page, OCR, or review state.

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
