# Local-First Roadmap Stage 8 Implementation Plan

Goal: add Direction Studio with persisted segment delivery controls, deterministic local inference, and stale render fingerprinting.

## Scope

- Add `segment_directions` records with direction payload, source, lock state, and fingerprint.
- Expand `DirectionProfile` with controlled emotion and pause controls.
- Add APIs to list, read, save, and infer segment directions.
- Add Direction Studio controls in the structure editor.
- Resolve production direction from segment override, segment direction, project default, then neutral default.
- Compare resolved direction in production status so edits stale affected renders.
- Document API, schema, UI behavior, and production resolution.

## Implementation Notes

- Emotion values are restricted to a small local taxonomy.
- Deterministic inference is local and does not require model downloads.
- Manual saves lock direction rows; inference skips locked rows.
- Kokoro adapters currently preserve unsupported expressive controls in metadata while applying supported pace data.

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
