# Readiness QA

Stage 11 adds deterministic readiness reports for pre-export review.

## Scope

Readiness QA runs locally and checks:

- source and clean-text state
- chapter, scene, and segment structure
- unresolved parser warnings
- speaker attribution review state
- narrator voice configuration
- character voice coverage
- narrator fallback rows from unvoiced or narrator-approved cast rows
- segment direction coverage
- chapter and segment audio artifacts, including real loudness/dead-air metrics (Phase 2
  task B2/G11): `chapter_audio_hot_{chapterId}` warns when a chapter's peak level exceeds
  the -3 dBFS mastering ceiling, and `chapter_audio_dead_air_{chapterId}` warns when the
  chapter WAV contains a genuine interior dead-air stretch (see
  [qa-rulebook.md](./qa-rulebook.md) for the exact thresholds, computed by
  `echodraft_api.audio_analysis`). Both checks keep the same id whether they pass or fail,
  per the stable-id-plus-`reason`-metadata convention below.
- stale segment renders
- export blockers such as rights and open blocking issues

## Reports

Reports are persisted in `readiness_reports` and include:

- overall status: `ready`, `needs_review`, or `blocked`
- score
- summary counts (`passed`, `warnings`, `blocking`, `accepted`, `total`)
- individual checks
- linked review issue IDs when a check needs action

Readiness issue rows are deduplicated by check ID and scope, so the same finding keeps a
stable row across reruns. Every run **re-derives state from the live checks** rather than
trusting a stale status string — a resolution is never allowed to hide a check that is still
failing.

Reviewers can mark linked issues as:

- `resolved` — a *claim that the underlying condition is fixed*. It is re-verified on every
  run: if the check still fails, the issue is reopened (`status` back to `open`) and the
  re-surfaced check carries `"reopened": true` in its metadata.
- `ignored` / `locked` — *accept-risk*. These stay excluded from the blocking/warning counts
  but are counted separately in `summary["accepted"]` and remain visible in the checks list
  (in the dashboard's "Accepted risks" section). They are acknowledged, not silently gone.

State also moves the other way automatically:

- **Auto-resolve on pass:** when a check now passes and a lingering issue row exists for its
  dedupe key, the issue is set to `resolved` automatically.
- **Patch re-verifies:** after a successful segment patch, a render-QA issue (one whose
  metadata carries a `segmentRenderId`) is auto-resolved when the fresh render's QA produced
  no open issue of the same category. The resolved issue records `"resolvedBy": "rerender"`
  and the `"newRenderId"` in its metadata.

## API

- `POST /api/v1/projects/{projectId}/readiness/run`
- `GET /api/v1/projects/{projectId}/readiness/latest`
- `GET /api/v1/projects/{projectId}/readiness/reports`

The run request may include `chapterId` to scope checks to a single chapter.

## Dashboard

The Readiness Report panel lives in Review & Patch. It runs the report, shows summary counts
and active findings, and exposes Resolve, Accept risk, and Lock actions for linked issues.
Accepted risks are listed in a separate "Accepted risks" section. After any of these actions,
and after a patch, the panel re-runs readiness so the badge and score are derived server-side
rather than from an optimistic local guess.
