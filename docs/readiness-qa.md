# Readiness QA

Stage 11 adds deterministic readiness reports for pre-export review.

## Scope

Readiness QA runs locally and checks:

- source and clean-text state
- chapter, scene, and segment structure
- unresolved parser warnings
- speaker attribution review state
- narrator voice configuration
- segment direction coverage
- chapter and segment audio artifacts
- stale segment renders
- export blockers such as rights and open blocking issues

## Reports

Reports are persisted in `readiness_reports` and include:

- overall status: `ready`, `needs_review`, or `blocked`
- score
- summary counts
- individual checks
- linked review issue IDs when a check needs action

Readiness issues use the existing review issue workflow. Reviewers can mark linked issues as:

- `resolved`
- `ignored`
- `locked`

These statuses survive reruns because readiness issue rows are deduplicated by check ID and scope.

## API

- `POST /api/v1/projects/{projectId}/readiness/run`
- `GET /api/v1/projects/{projectId}/readiness/latest`
- `GET /api/v1/projects/{projectId}/readiness/reports`

The run request may include `chapterId` to scope checks to a single chapter.

## Dashboard

The Readiness Report panel lives in Review & Patch. It runs the report, shows summary counts and findings, and exposes Resolve, Ignore, and Lock actions for linked issues.
