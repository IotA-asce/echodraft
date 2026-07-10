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
6. `sound_plan_manifest.json`
7. `chapter_assembly_manifest.json`
8. `qa_manifest.json`
9. `export_manifest.json`

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
Purpose: capture ingestion output. Current `schemaVersion`: `0.2.0` (added
`structureSignalsPath`).

Payload fields:
- source document metadata
- normalized text artifact path
- `structureSignalsPath` — path to `chapter_signals.json` (container chapter
  signals from DOCX heading styles / EPUB spine + TOC), or `null` when the
  container carried no structural metadata (e.g. plain `.txt`). The DB stores
  only this path (`source_documents.structure_signals_path`); the signal payload
  lives on the filesystem under `sources/{sourceId}/structure_signals/`.
- chapter boundary hints
- parser warnings
- checksum

Each entry in `chapter_signals.json` has the shape:

```json
{"title": "The Arrival", "sourceKind": "docx_heading", "level": 1, "anchorText": "The Arrival", "confidence": 0.95}
```

`sourceKind` is one of `docx_heading` (Title→level 0/0.9, Heading 1→level 1/0.95,
Heading 2→level 2/0.75), `epub_toc` (0.95), or `epub_spine` (first `<h1>` of a
spine item not already covered by TOC, 0.8). Signals resolve to chapters by
case-insensitive, whitespace-collapsed **anchor-text** match against parsed
blocks — never by raw offsets, which cleaning shifts. Only `level <= 1` promotes
a chapter; level 2 is a scene-break hint recorded on the signal but not a
chapter in the current parser.

### Structure manifest
Purpose: capture chapter, scene, and segment structure.

Payload fields:
- parser version and compiler pipeline (includes the `container_chapter_signals`
  stage, which promotes source-manifest chapter signals to chapter boundaries)
- structure quality metrics (includes `chaptersFromContainerSignals`, the count
  of chapters opened by a container signal rather than by an in-text keyword)
- parser diagnostics and warning evidence (a signal matching no block emits a
  `container_signal_unmatched` warning)
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

### Sound plan manifest
Purpose: record deterministic, chapter-scoped automatic sound decisions before mixing.

Current `schemaVersion`: `0.1.0`.

Payload fields:
- render mode and accepted per-scene atmosphere profiles
- ordered planned ambience/SFX cues with deterministic plan keys and evidence
- SFX budget limit/usage and explicit skip reasons
- materialized Tier-0 asset and cue IDs

Every run writes an immutable `sound_plan_manifest.<id>.json` and refreshes the chapter's
`sound_plan_manifest.json` latest pointer. A clean-narration (`speech_only`) plan is empty and does
not mutate cinematic cues.

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
- output roles (`chapter`, `audiobook`, `retail_sample`) with bytes, duration, SHA-256, package-relative `artifactPath`, and local `artifactUrl`
- export QA scorecard with loudness target, true-peak ceiling, per-output measurements, and pass/fail summary

Current export manifest schema:
- `schemaVersion: "0.3.0"`
- `qa.targetLufs: -19.0`
- `qa.lufsTolerance: 1.0`
- `qa.truePeakCeilingDb: -3.0`
- `qa.outputs[]` entries include `filename`, `method`, `durationMs`, `bytes`, `sha256`, `withinTolerance`, and measured loudness/peak fields when FFmpeg can measure them
- M4B package outputs use `role: "audiobook"` and carry chapter marker source metadata
- M4B outputs include `artifactUrl` so the chapter-marked audiobook is directly addressable in addition to being included in the ZIP package
- optional retail samples use `role: "retail_sample"` and reference the source chapter

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
