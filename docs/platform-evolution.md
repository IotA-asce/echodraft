# Platform Evolution

See also: [project-overview.md](project-overview.md), [architecture.md](architecture.md), [repository-blueprint.md](repository-blueprint.md), [plans/phase-roadmap.md](../plans/phase-roadmap.md)

## Purpose
This document defines the post-MVP evolution path from a local-first creator tool into a broader audiobook production platform for publishers, studios, and enterprise teams.

## Future target users
- Indie authors using solo creator mode
- Small and medium publishers managing multiple titles
- Audio producers and studios using an editorial workspace
- Enterprise rights holders operating at catalog scale
- Localization and accessibility teams

## Product modes beyond MVP
### Solo creator mode
- Keeps the local-first workflow intact
- Adds better templates, stronger previews, and improved polish

### Publisher mode
- Adds title pipeline management, approvals, rights workflows, and operational visibility

### Studio mode
- Adds deeper editorial review, collaboration, assignments, and handoff workflows

### API and platform mode
- Exposes core ingestion, structure, casting, rendering, QA, and export flows through platform APIs

## Future capabilities
### Rights and licensing
- rights evidence capture
- consent tracking
- auditability
- export enforcement policies

### Collaboration
- user and organization accounts
- review assignments
- approvals
- shared comments and issue queues

### Catalog-scale processing
- worker fleets
- queued batch processing
- multi-title throughput management
- project and render analytics

### Cross-title continuity
- reusable voice libraries
- character continuity across series
- shared pronunciation dictionaries

### Localization and language support
- per-locale voice configurations
- pronunciation and style variations by language
- export packaging for multi-language catalogs

### Platform distribution
- API access
- integration with downstream distribution tools
- publisher-grade packaging and metadata workflows

## Hosted architecture evolution
The hosted form of the system replaces the single-node runtime with:
- API layer
- Postgres
- object storage
- queue infrastructure
- dedicated workers for ingestion, narrative, TTS, assembly, QA, and export

This evolution must preserve the same segment-first, manifest-driven workflow already established in MVP. The pipeline gets distributed; it does not become a one-shot black box.

## New entities introduced later
Expected additions after MVP:
- organizations
- users
- memberships
- audit logs
- review assignments
- API keys
- billing accounts
- asset permissions

These are intentionally excluded from MVP database and API scope.

## Quality levels
### AI draft
- fast, editable, and patch-oriented

### Producer polish
- better QA, tighter performance tuning, stronger review controls

### Publisher release
- rigorous approvals, rights traceability, operational controls, and higher consistency thresholds

## Guardrails for future work
- Do not let future SaaS concerns distort the MVP storage and editing model.
- Do not collapse chapter/scene/segment structure into opaque batch jobs.
- Do not replace append-only render history with overwrite semantics.
- Do not move audio artifacts into relational BLOB storage for convenience.
- Do not assume collaboration or rights workflows exist in the MVP codebase unless explicitly implemented.
