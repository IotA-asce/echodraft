# Initial Backlog Seed

See also: [foundation-sprint-plan.md](foundation-sprint-plan.md), [mvp-execution-plan.md](mvp-execution-plan.md), [../docs/api-spec.yaml](../docs/api/api-spec.yaml)

## Priority model
- `P0`: blocks the MVP foundation or next sprint
- `P1`: should land in the named sprint
- `P2`: useful but can slip without breaking the phase

## Sprint 0 backlog
### P0
- Bootstrap `apps/api` with FastAPI entrypoint and health route.
- Bootstrap `apps/web` with Next.js shell and project list page.
- Create `libs/domain-models` with shared project and job schemas.
- Create `libs/db` with SQLite setup and first migration set.
- Implement `POST /api/v1/projects` and `GET /api/v1/projects`.
- Create project artifact directory on project creation.

Acceptance outcome:
- project creation works through API and appears in UI

### P1
- Add persisted `jobs` table and `GET /api/v1/jobs/{jobId}` endpoint.
- Add structured logging baseline.
- Add seed script for a sample project.

Acceptance outcome:
- project lifecycle and job status are inspectable locally

## Sprint 1 backlog
### P0
- Implement TXT, Markdown, DOCX, and EPUB importers.
- Define canonical manuscript artifact format.
- Implement `/api/v1/projects/{projectId}/source/import`.
- Store `source_manifest.json` and parser warnings.

Acceptance outcome:
- manuscript import succeeds for core fixtures

### P1
- Implement reparse endpoint and parser warning presentation in UI.

Acceptance outcome:
- user can retry import and review warnings

## Sprint 2 backlog
### P0
- Implement chapter boundary detection.
- Implement scene segmentation heuristics.
- Implement segment generation rules.
- Persist chapters, scenes, and segments.
- Implement chapter, scene, and segment listing endpoints.

Acceptance outcome:
- manuscript is browseable as chapters/scenes/segments

### P1
- Add manual segment text editing and structure manifest generation.
- Add initial character candidate extraction.

Acceptance outcome:
- structure can be corrected without reimporting source

## Sprint 3 backlog
### P0
- Implement character CRUD.
- Implement voice profile CRUD.
- Implement character-to-voice assignment.
- Implement pronunciation CRUD.
- Generate initial voice bible artifact.

Acceptance outcome:
- narrator and several characters are mapped to stable voice profiles

### P1
- Add preview-first casting UI and low-confidence attribution surfacing.

Acceptance outcome:
- casting choices are reviewable before long-running generation

## Dependency order
1. project and artifact bootstrap
2. source import
3. structure extraction
4. casting and pronunciation
5. direction and rendering

Do not start full rendering work before the structure and casting contracts are stable enough to support segment-level patching.
