# Pipeline Manifest Spec

See also: [architecture.md](architecture.md), [domain-model.md](../domain/domain-model.md), [db-schema.md](../domain/db-schema.md), [api-spec.yaml](../api/api-spec.yaml)

## Purpose
Pipeline manifests make each stage resumable, inspectable, and reproducible. Every stage consumes a manifest and emits a manifest for the next stage or review step.

## Principles
- Use JSON manifests for runtime simplicity.
- Version every manifest schema.
- Reference artifacts by durable path or URI.
- Include diagnostics; do not discard them.
- Mark stage completion only after referenced artifacts exist.

## Manifest types
1. `source_manifest.json`
2. `structure_manifest.json`
3. `casting_manifest.json`
4. `direction_manifest.json`
5. `segment_render_manifest.json`
6. `chapter_assembly_manifest.json`
7. `qa_manifest.json`
8. `export_manifest.json`

## Common envelope
Every manifest must include:

```json
{
  "manifestType": "structure_manifest",
  "schemaVersion": "0.1.0",
  "projectId": "proj_001",
  "chapterId": "chap_001",
  "generatedAt": "2026-03-17T12:00:00Z",
  "generator": {
    "service": "narrative-service",
    "version": "0.1.0"
  },
  "status": "completed",
  "diagnostics": [],
  "payload": {}
}
```

Required fields:
- `manifestType`
- `schemaVersion`
- `projectId`
- `generatedAt`
- `status`
- `payload`

Optional but recommended:
- `chapterId`
- `segmentId`
- `generator`
- `inputHashes`
- `diagnostics`

## Stage manifests
### Source manifest
Purpose: capture ingestion output.

Payload fields:
- source document metadata
- normalized text artifact path
- chapter boundary hints
- parser warnings
- checksum

### Structure manifest
Purpose: capture chapter, scene, and segment structure.

Payload fields:
- parser version and compiler pipeline
- structure quality metrics
- parser diagnostics and warning evidence
- character candidates
- scene list
- segment list with parser evidence and source-span IDs
- speaker attribution confidence

### Casting manifest
Purpose: record narrator and character voice assignments.

Payload fields:
- narrator voice profile
- character voice assignments
- pronunciation dictionary version

### Direction manifest
Purpose: record scene defaults and segment overrides.

Payload fields:
- per-scene defaults
- per-segment overrides
- pacing and pause settings
- ambience suggestion hints

### Segment render manifest
Purpose: record a single segment generation output.

Payload fields:
- render request config
- render key
- audio artifact paths
- alignment path
- diagnostics

### Chapter assembly manifest
Purpose: record chapter-level assembly.

Payload fields:
- ordered segment render list
- inserted pauses
- ambience asset references
- output stem and mix paths

### QA manifest
Purpose: summarize automated QA findings.

Payload fields:
- issue summary
- warnings and errors
- objective checks
- pass/fail or blocking status

### Export manifest
Purpose: describe final export package.

Payload fields:
- export format
- source chapter renders
- metadata used
- output file paths

## Validation rules
- `manifestType`, `schemaVersion`, `projectId`, and `payload` are required.
- Referenced artifacts must exist before the stage is `completed`.
- Diagnostics must be persisted even when the stage succeeds.
- A downstream stage may not silently ignore upstream warnings that materially affect correctness.

## Invalidation and rerun rules
### Source changes
If normalized text changes:
- invalidate all structure manifests for affected chapters
- invalidate downstream casting, direction, render, assembly, QA, and export artifacts for affected scope

### Structure changes
If chapter, scene, or segment boundaries change:
- preserve prior manifests and renders for auditability
- mark downstream casting/direction/render outputs stale for affected chapters

### Casting changes
If narrator or character voice assignments change:
- narrator change may stale the full title
- character voice change stales only affected segments and downstream chapter outputs

### Pronunciation changes
If pronunciation entries change:
- invalidate only segments containing impacted terms
- stale downstream chapter, QA, and export artifacts derived from those segments

### Direction changes
If scene defaults or segment overrides change:
- invalidate affected segment renders
- stale affected chapter assembly, QA, and export artifacts

### Segment regeneration
If a segment is regenerated:
- append a new segment render record
- update the active render pointer
- stale any chapter render that references the older active render
- require targeted QA rerun for affected chapter scope

### Chapter reassembly
If chapter assembly changes without new segment renders:
- preserve prior chapter render history
- rerun chapter QA
- stale exports derived from superseded chapter renders

### Export changes
If export packaging config changes:
- rerun export packaging
- rerun export-level validation only
- do not invalidate upstream segment or chapter renders

## Completion semantics
A stage is complete only when:
- the manifest is written,
- all referenced artifacts exist,
- the database state is updated where applicable,
- the job status is terminal,
- diagnostics are attached.
