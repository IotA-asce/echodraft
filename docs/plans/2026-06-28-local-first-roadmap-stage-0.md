# Local-First Roadmap Stage 0 Implementation Plan

Goal: harden and document the current alpha pipeline before replacing major subsystems in later roadmap stages.

## Scope

- Document the current ingestion, PDF/OCR, structure, TTS, review, QA, assembly, and export behavior.
- Add regression tests for current limitations and invariants.
- Do not change production behavior in this stage.
- Do not add frontend dependencies or touch the pre-existing local `package-lock.json` change.

## Implementation Notes

- `docs/current-pipeline-behavior.md` is the current-state reference for later stages.
- Ingestion tests now describe page-marker pollution as current behavior, not desired future behavior.
- OCR tests use mocks for scanned and mixed PDF paths so committed tests do not require local private assets or external binaries.
- Production tests verify that render cache hits do not create new rows, forced renders create append-only lineage, and open blocking issues gate export.

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
