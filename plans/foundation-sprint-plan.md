# Foundation Sprint Plan

See also: [mvp-execution-plan.md](mvp-execution-plan.md), [backlog-seed.md](backlog-seed.md), [../docs/repository-blueprint.md](../docs/architecture/repository-blueprint.md)

## Sprint goal
Establish the minimum repo, runtime, and persistence skeleton needed to support project creation and local artifact management.

## Target outcomes
By the end of Sprint 0:
- the monorepo skeleton exists
- `apps/api` serves the MVP API shell
- `apps/web` renders the basic project UI shell
- `libs/domain-models` defines shared core entities
- `libs/db` owns the initial schema and migration chain
- local project directories can be created on demand
- long-running work has a job runner skeleton and status model

## Workstreams
### Repo bootstrap
- Create `apps/api`, `apps/web`, `services/*`, `libs/domain-models`, and `libs/db`.
- Add root tooling for Python and Node package management.
- Add basic developer scripts for booting API, web, and database tasks.

### API shell
- Stand up FastAPI entrypoint in `apps/api`.
- Implement health route and project CRUD shell.
- Wire request and response models to shared domain schemas.

### Web shell
- Stand up Next.js app in `apps/web`.
- Create project dashboard shell with list and create flow.
- Add job polling and project status placeholders, even if backed by stub data first.

### Domain models
- Define shared enums and entity schemas for `Project`, `Chapter`, `Scene`, `Segment`, `Character`, `VoiceProfile`, `Issue`, `ExportPackage`, and `RightsDeclaration`.
- Keep field names aligned with [../docs/domain-model.md](../docs/domain/domain-model.md) and [../docs/api-spec.yaml](../docs/api/api-spec.yaml).

### Database and migrations
- Bootstrap SQLite connection and Alembic in `libs/db`.
- Implement initial migrations for `projects`, `jobs`, and `rights_declarations`.
- Add repository layer for project persistence.

### Artifact layout
- Define local artifact root structure under a configurable base directory.
- Create project directories on project creation.
- Persist source-of-truth artifact paths in DB rows rather than embedding binary data in tables.

### Logging and jobs
- Add structured logging with correlation by `project_id` and `job_id`.
- Implement a simple in-process job runner skeleton with persisted job states.
- Expose job status through the API contract.

### Seed and fixtures
- Add a sample project seed script.
- Add minimal fixture content for manual smoke testing.

## Validation targets
Run at minimum:
- backend tests for project creation and job status
- lint and typecheck for the backend shell
- frontend lint/typecheck for the web shell
- smoke test that project creation creates both DB state and local artifact directory

## Exit criteria
- project creation persists to SQLite
- project list renders in the UI
- artifact directory is created for each project
- job status endpoint returns structured output
- no cloud dependency is required for the foundation workflow
