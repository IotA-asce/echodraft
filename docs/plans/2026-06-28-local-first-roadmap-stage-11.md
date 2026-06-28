# Stage 11 - Readiness QA

Goal: add deterministic production readiness checks, persisted readiness reports, and review controls for resolving, ignoring, or locking findings.

## Scope

- Add persisted `readiness_reports` snapshots.
- Run deterministic checks for text, structure, speaker, voice, direction, audio, stale renders, and export blockers.
- Link failed checks to review issues while preserving user resolution statuses across reruns.
- Expose readiness run/latest/history APIs.
- Add a dashboard Readiness Report panel with Resolve, Ignore, and Lock controls.

## Validation

- Add API regression tests for report persistence and issue resolution preservation.
- Run backend tests, Ruff, mypy, web typecheck, web lint, and targeted smoke testing where available before merge.

## Boundaries

- No cloud QA or LLM judging is added.
- Readiness checks are conservative and deterministic.
- Existing review issues remain the actionable resolution surface.
