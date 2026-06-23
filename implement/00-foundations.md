# Stage 00 — Foundations

## Outcome

Provide a local-first monorepo in which a user can create and list projects, each backed by SQLite records and a local artifact directory.

## Implement

- Create `apps/api` as a FastAPI service with `/health`, `POST /api/v1/projects`, `GET /api/v1/projects`, and `GET /api/v1/jobs/{job_id}`.
- Create `apps/web` as a Next.js application with a project list, project-creation form, empty/loading/error states, and job-status placeholders.
- Create `libs/domain-models` for shared Pydantic/domain definitions: `Project`, `Job`, `RightsDeclaration`, `Chapter`, `Scene`, `Segment`, `Character`, `VoiceProfile`, `Issue`, and `ExportPackage`.
- Create `libs/db` with SQLite connection handling, Alembic migrations, repository functions, and initial `projects`, `jobs`, and `rights_declarations` tables.
- Define a configurable artifact root. On project creation, make `<artifact-root>/<project-id>/` with `source/`, `structure/`, `audio/`, `exports/`, `logs/`, and `manifests/` subdirectories.
- Persist only metadata and artifact paths in SQLite; never store source documents or audio blobs in database columns.
- Implement structured JSON logging with `project_id`, `job_id`, request ID, event name, and error fields.
- Implement an in-process job runner with durable states: `queued`, `running`, `succeeded`, `failed`, and `cancelled`.
- Add a sample-project seed command and fixture manuscript for manual smoke tests.

## Validation

- Unit-test project creation, rights validation, artifact-directory creation, and job-state transitions.
- Run an API-to-DB integration test against a temporary SQLite database.
- Add a browser smoke test: create a project, verify it appears in the list, and verify its artifact directory exists.

## Done when

`POST /projects` creates a durable project, the web UI displays it, and the job-status endpoint returns a structured response without any cloud dependency.
