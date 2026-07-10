# Local-First Roadmap Stage 7 Implementation Plan

Goal: add deterministic speaker attribution, reviewable cast decisions, and production voice resolution from approved speaker assignments.

## Scope

- Add `speaker_attributions` records for segment speaker decisions.
- Generate deterministic attributions from parser speaker candidates.
- Keep low-confidence or unmatched dialogue in a review queue.
- Add optional Ollama fallback through the local LLM service.
- Add Cast Review dashboard controls for assigning characters, approving narrator rows, and locking review decisions.
- Resolve production voices from approved character attributions while preserving segment override precedence.
- Document the API, data model, and production behavior.

## Implementation Notes

- One active attribution row is stored per segment.
- Locked rows are skipped by reruns so user decisions survive parser and LLM passes.
- The local LLM fallback is explicit and schema-constrained; no cloud fallback is introduced.
- Render freshness already keys on resolved voice profile, so changed speaker voice resolution marks only affected segment renders stale.

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
