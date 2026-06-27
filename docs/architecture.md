# Architecture

See also: [domain-model.md](domain-model.md), [db-schema.md](db-schema.md), [pipeline-manifest-spec.md](pipeline-manifest-spec.md), [repository-blueprint.md](repository-blueprint.md)

## Architectural goal
Build a local-first audiobook production system that can turn long-form manuscripts into patchable, multi-voice chapter drafts while remaining:
- resumable,
- inspectable,
- debuggable,
- safe to rerun at segment scope,
- practical on a single Apple Silicon machine.

## Primary architectural decisions
### Segment-first architecture
`Segment` is the smallest editable, renderable, QA-able, and patchable unit. All downstream invalidation rules anchor on segment changes.

### Manifest-driven pipeline
Each major stage consumes a structured manifest and emits a structured manifest. A stage is not considered complete unless its manifest and referenced artifacts are durable.

### Artifact separation
- Database: metadata, state, jobs, entity relationships, issue tracking
- Filesystem/object storage: normalized text, manifests, render artifacts, waveforms, exports

### Append-only render history
Regeneration creates a new `segment_renders` row and a new artifact path. Existing renders remain traceable for debugging and comparison.

### Human-in-the-loop review
The system is designed to draft, surface uncertainty, and support correction. It is not a fire-and-forget renderer.

### Local-first MVP
The MVP must work without mandatory cloud services. Hosted evolution is additive, not foundational.

## MVP runtime architecture
```text
[Next.js / React UI]
        |
        v
[FastAPI Backend]
        |
        +--> Project API
        +--> Ingestion Module
        +--> Narrative Module
        +--> Casting Module
        +--> Direction Module
        +--> TTS Module
        +--> Assembly Module
        +--> QA Module
        +--> Review Module
        +--> Export Module
        +--> Local AI / Model Center
        |
        +--> SQLite
        +--> Local Artifact Store
        +--> Local Model Runtime
```

## Service boundaries
### Ingestion
- import manuscript files
- normalize text
- persist PDF page images/text/OCR metadata when available
- detect chapters
- persist canonical manuscript references

### Narrative
- split chapters into scenes and segments
- detect dialogue
- derive character candidates
- score attribution confidence

### Casting
- manage narrator and character voice profiles
- map characters to voices
- maintain the voice bible and pronunciation dictionary

### Direction
- compute scene defaults
- manage per-segment overrides
- carry pacing, energy, pause, and ambience guidance

### TTS
- expose backend-agnostic synthesis contracts
- generate per-segment audio
- persist alignment, waveform, and diagnostics

### Local AI / Model Center
- maintain the local model and tool catalog
- install and verify supported local system tools and model runtimes
- report capability health to ingestion, LLM, TTS, and audio workflows
- persist installation state and setup logs

### Audio assembly
- order active segment renders
- insert pauses and transitions
- assemble speech and optional ambience stems
- create chapter mix artifacts

### QA
- run technical, linguistic, and narrative checks
- open issues against project/chapter/segment anchors

### Review
- manage comments, review state, and patchability workflow

### Export
- build WAV, MP3, and M4B packages
- attach metadata
- gate export on rights and QA state

## Processing pipeline
1. Import source
2. Normalize manuscript
3. Split chapters
4. Split scenes
5. Extract segments
6. Build character registry
7. Assign speaker candidates
8. Assign voice profiles
9. Apply pronunciation rules
10. Apply direction rules
11. Generate segment audio
12. Assemble speech stem
13. Layer ambience when enabled
14. Run QA checks
15. Review and patch
16. Export package

## Stage outputs
### Ingestion
- canonical manuscript artifact
- source page records and page artifacts for PDF imports
- OCR run/results when scanned pages require local OCR
- canonical span mappings from source pages to selected text
- source manifest

### Structure
- chapter, scene, and segment records
- structure manifest
- character candidate set

### Casting and direction
- voice profile assignments
- pronunciation set
- casting and direction manifests

### Generation
- immutable segment render artifacts
- alignment and waveform files
- segment render manifest

### Assembly and QA
- chapter speech/ambience/mix artifacts
- chapter assembly manifest
- QA manifest and issue set

### Export
- export package
- export manifest

## Storage layout
### Database responsibilities
- project metadata and lifecycle state
- structure entities
- voice/casting state
- issue, comment, and review state
- job status and export records

### Artifact store responsibilities
- source files
- normalized text
- manifests
- segment audio renders
- alignment JSON
- waveforms
- chapter stems and mixes
- export files
- debug bundles

## Caching
Segment render caching uses a deterministic key derived from:
- normalized segment text
- voice profile configuration
- direction settings
- pronunciation dictionary version
- backend name
- backend model version

Cache hits avoid repeated inference during patch loops. Cache entries must still map to immutable render history.

## Failure handling
- Every expensive operation is a job.
- Jobs write progress and final status.
- A failed job must not corrupt prior valid outputs.
- Partial downstream outputs are invalid until their manifest is complete.
- Regeneration invalidates only affected downstream artifacts.

## Invalidation rules
- Segment text, speaker, voice, pronunciation, or direction changes stale the active segment render.
- New active segment renders stale any chapter render that includes the segment.
- Narrator changes may stale all chapters in the project.
- Exports always point to a specific approved chapter render set; they are never floating references.

## Observability
- structured logs from day one
- job progress tracking
- diagnostics stored in manifests
- debug bundles for failed or suspicious runs

## Hosted evolution path
The future hosted system keeps the same contracts but distributes execution across:
- API layer
- Postgres
- object storage
- queue/worker system
- dedicated ingestion, narrative, TTS, assembly, QA, and export workers

The move to hosted infrastructure must preserve:
- segment-first editing,
- manifest-driven stage boundaries,
- append-only render history,
- patchability over one-shot generation.
