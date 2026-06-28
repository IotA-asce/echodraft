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
- clean page markers, repeated headers/footers, broken wraps, and simple hyphenation before normalization
- normalize text
- persist PDF page images/text/OCR metadata when available
- persist clean-text review issues separately from canonical manuscript text
- persist canonical manuscript references

### Narrative
- split chapters into scenes and segments
- detect dialogue
- surface parser warnings with evidence and confidence
- preserve user locks across parser reruns
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
- register local providers: mock, Kokoro, Piper, and consent-gated XTTS-v2
- generate per-segment audio
- persist render metadata, provider provenance, queue status, and diagnostics
- fail closed when a configured local provider is missing files, tools, or required consent

### Local AI / Model Center
- maintain the local model and tool catalog
- install and verify supported local system tools and model runtimes
- run schema-constrained local LLM extraction jobs through Ollama
- provide local embeddings without cloud fallback
- report capability health to ingestion, LLM, TTS, and audio workflows
- persist installation state and setup logs

### Audio assembly
- order active segment renders
- insert pauses and transitions
- assemble speech and optional ambience stems
- create chapter mix artifacts
- import local WAV sound assets and apply scene cues only for explicit light/dramatized mixes

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
2. Extract source text and page/OCR metadata
3. Clean and normalize manuscript
4. Split chapters
5. Split scenes
6. Extract segments
7. Build character registry
8. Assign speaker candidates
9. Assign voice profiles
10. Apply pronunciation rules
11. Apply direction rules
12. Generate segment audio
13. Assemble speech stem
14. Layer ambience when enabled
15. Run QA checks
16. Review and patch
17. Export package

## Stage outputs
### Ingestion
- canonical manuscript artifact
- source page records and page artifacts for PDF imports
- OCR run/results when scanned pages require local OCR
- canonical span mappings from source pages to selected text
- cleaning manifest and clean-text review issues
- source manifest

### Structure
- chapter, scene, and segment records
- parser warnings and parser evidence
- user locks for approved structure decisions
- structure manifest
- character candidate set

### Casting and direction
- voice profile assignments
- pronunciation set
- casting and direction manifests

### Local LLM
- LLM run records
- prompt, schema, response, and result artifacts
- fail-closed validation status

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
- Segment text, approved speaker attribution, voice, pronunciation, direction, active provider, or provider model identity changes stale the active segment render.
- Voice resolution precedence is segment override, approved character speaker attribution, then project narrator.
- Direction resolution precedence is segment production override, Segment Direction record, project default, then neutral segment default.
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
