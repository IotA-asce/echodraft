# Repository Blueprint

See also: [architecture.md](architecture.md), [domain-model.md](domain-model.md), [../AGENTS.md](../AGENTS.md), [../plans/foundation-sprint-plan.md](../plans/foundation-sprint-plan.md)

## Purpose
This blueprint defines the intended monorepo structure for `echodraft` and maps the product architecture onto repo ownership boundaries. It is aligned with the repo layout already declared in `AGENTS.md`.

## Target top-level layout
```text
apps/
  api/                  FastAPI entrypoint and HTTP composition root
  web/                  Next.js application for the editor and review UI

services/
  ingestion-service/    Source import and normalization
  narrative-service/    Chapter, scene, and segment structuring
  casting-service/      Character, voice, and pronunciation logic
  direction-service/    Scene defaults and segment delivery rules
  tts-service/          Backend-agnostic segment synthesis
  audio-assembly-service/
                        Speech and ambience assembly
  qa-service/           Automated QA and issue creation
  review-service/       Comments, review state, and patch workflows
  export-service/       WAV/MP3/M4B packaging
  rights-service/       Rights gating and declaration logic

libs/
  domain-models/        Shared Pydantic/domain schemas and enums
  db/                   ORM models, migrations, repositories

docs/                   Product and engineering source of truth
plans/                  Sequenced execution plans and backlog seeds
```

## Ownership rules
### `apps/api`
- own REST routing, request validation, auth stubs if later needed, and job submission endpoints
- compose service modules, but do not hold domain logic

### `apps/web`
- own user flows, editor screens, and async job polling UX
- consume API contracts from [api-spec.yaml](api-spec.yaml)

### `services/*`
- own domain behavior for each processing stage
- stay modular and stage-oriented
- write manifests and artifacts through shared libraries instead of duplicating persistence code

### `libs/domain-models`
- own shared entity shapes, enums, manifest envelopes, and request/response models that must stay consistent across services and apps

### `libs/db`
- own persistence schema, migration order, repositories, and lifecycle-safe database access
- never store audio blobs directly in relational tables

## Recommended service boundaries
- `ingestion-service`: source import, normalization, source manifest
- `narrative-service`: chapter/scene/segment detection, speaker attribution
- `casting-service`: character registry, voice assignments, pronunciation entries
- `direction-service`: scene mood, style defaults, segment-level overrides
- `tts-service`: adapter layer, render key generation, segment render persistence
- `audio-assembly-service`: chapter stems, mix output, ambience layering
- `qa-service`: automated checks, issue creation, threshold evaluation
- `review-service`: comments, review actions, stale render handling
- `export-service`: package generation, metadata, final export artifacts
- `rights-service`: declaration storage and export gating

## Local artifact layout
Code and runtime artifacts are related but must remain separate:
- repo code lives inside the monorepo
- project runtime artifacts live in a local artifact root outside normal code packages

Recommended runtime artifact shape:
```text
projects/
  <project-id>/
    source/
    manifests/
    chapters/
      <chapter-id>/
        segments/
        stems/
        mixes/
    exports/
    debug/
```

Rules:
- database rows reference artifact paths
- manifests live with project artifacts, not in the relational DB
- scripts may reindex artifacts, but must not rewrite render history

## Initial bootstrap guidance
Sprint 0 should create only the minimum agreed layout:
- `apps/api`
- `apps/web`
- `services/` directories for planned domains
- `libs/domain-models`
- `libs/db`
- `docs/`
- `plans/`

Do not add extra shared libraries until a concrete use appears. Keep the initial repo modular, but avoid premature fragmentation.

## Evolution notes
- `desktop-shell` can be added later if the local desktop wrapper becomes necessary.
- Additional shared libraries such as `audio-utils`, `tts-adapters`, `storage`, and `manifests` are expected later, but are not required to start the MVP repo.
- If services stay in-process during MVP, keep the same module boundaries so future extraction remains straightforward.
