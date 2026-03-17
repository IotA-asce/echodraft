# Phase Roadmap

See also: [mvp-execution-plan.md](mvp-execution-plan.md), [../docs/platform-evolution.md](../docs/platform-evolution.md)

## MVP phases
### Phase 0: Foundations
- repo bootstrap
- API and web shells
- SQLite and migration setup
- local artifact store
- job runner skeleton

Exit:
- projects can be created and persisted locally

### Phase 1: Ingestion and Narrative Structure
- manuscript import
- normalization
- chapter, scene, and segment extraction
- structure manifest generation

Exit:
- a manuscript becomes a structured project

### Phase 2: Casting and Direction
- character registry
- voice profile management
- narrator and character mapping
- pronunciation dictionary
- scene and segment direction rules

Exit:
- a project has a stable voice bible and render directives

### Phase 3: Segment Generation and Chapter Assembly
- TTS adapter layer
- segment rendering
- immutable render history
- chapter assembly and playback

Exit:
- one chapter can be generated end-to-end

### Phase 4: Review, Patch, and QA
- issue system
- comments
- automated QA
- selective regeneration
- stale chapter handling

Exit:
- bad lines can be patched without rerendering the full title

### Phase 5: Export and MVP Hardening
- export packaging
- rights gating
- alpha stabilization
- sample-book matrix

Exit:
- external testers can complete the MVP workflow

## Post-MVP platform phases
### Phase 6: Hybrid or cloud transition
- queue-backed workers
- Postgres and object storage
- separately runnable services

### Phase 7: Publisher features
- collaboration
- approvals
- rights workflows
- org/user management

### Phase 8: Catalog-scale and localization
- batch processing
- reusable voice libraries
- localization workflows
- platform APIs

## Decision boundaries
Use MVP phases when a task is required for:
- local-first project creation
- manuscript-to-chapter workflow
- segment patching
- exportable draft quality

Treat work as post-MVP when it depends on:
- cloud-only infrastructure
- multi-user collaboration
- enterprise rights operations
- catalog-scale orchestration
- monetization or billing
