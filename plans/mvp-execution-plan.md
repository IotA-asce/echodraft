# MVP Execution Plan

See also: [foundation-sprint-plan.md](foundation-sprint-plan.md), [backlog-seed.md](backlog-seed.md), [../docs/mvp-product-spec.md](../docs/mvp-product-spec.md)

## Goal
Ship a usable local-first MVP that lets a user create a project, import a manuscript, structure it into chapters/scenes/segments, assign voices, generate a chapter, selectively regenerate bad lines, and export chaptered audio.

## Team assumption
Ideal small team:
- 1 full-stack or backend-heavy engineer
- 1 ML/audio engineer
- optional design support

If solo, keep the same order and expand timelines rather than changing scope boundaries.

## Sprint structure
Assume 2-week sprints.

## Sprint 0: Foundations
Goals:
- establish repo, baseline tooling, and local runtime

Deliverables:
- working backend shell
- working frontend shell
- SQLite persistence
- local artifact directory creation
- structured logging
- job runner skeleton

Exit criteria:
- `POST /projects` works
- project list UI works
- local project directory is created successfully

## Sprint 1: Ingestion
Goals:
- import source files and normalize manuscript text

Deliverables:
- TXT, Markdown, DOCX, and EPUB import path
- canonical manuscript artifact
- source manifest generation
- parser warning surfacing

Exit criteria:
- at least TXT, DOCX, and EPUB import works on sample fixtures

## Sprint 2: Structure Extraction
Goals:
- convert manuscript into chapters, scenes, and segments

Deliverables:
- chapter/scene/segment viewer
- structure manifest generation
- editable segment records
- character candidate extraction scaffold

Exit criteria:
- a manuscript becomes a browsable structured project

## Sprint 3: Character Registry and Casting
Goals:
- create character map and voice assignment flow

Deliverables:
- character CRUD
- voice profile CRUD
- character-to-voice assignment
- pronunciation CRUD
- voice bible scaffold

Exit criteria:
- narrator plus several characters can be mapped to voices

## Sprint 4: Voice Preview and Direction
Goals:
- preview voices and encode delivery rules

Deliverables:
- TTS adapter interface
- mock adapter and first local adapter
- voice preview workflow
- scene defaults and segment override editing
- direction manifest generation

Exit criteria:
- user can preview a voice with style prompt and save direction settings

## Sprint 5: Segment Generation
Goals:
- generate audio at segment level

Deliverables:
- segment render request contract
- render key generation
- immutable render history
- waveform metadata
- single-segment generation endpoint and UI controls

Exit criteria:
- one segment can be rendered, replayed, and regenerated

## Sprint 6: Chapter Assembly
Goals:
- combine segment renders into chapter output

Deliverables:
- ordered segment retrieval
- pause insertion
- speech stem assembly
- chapter render records
- chapter playback UI

Exit criteria:
- one chapter can be generated from segment renders end-to-end

## Sprint 7: Review and Patch Loop
Goals:
- make bad lines easy to fix

Deliverables:
- issues and comments model/API
- automated QA for missing audio, clipping, silence, and truncation
- mark-reviewed flow
- selective patch workflow

Exit criteria:
- user can detect a bad line, regenerate it, and reassemble the chapter

## Sprint 8: Ambience and Light Cinematic Layer
Goals:
- add subtle production value without harming clarity

Deliverables:
- ambience profile model
- ambience asset referencing
- ambience stem assembly
- render modes for `speech_only`, `multi_voice`, and `light_cinematic`

Exit criteria:
- user can export with or without ambience

## Sprint 9: Export and Packaging
Goals:
- produce shareable audio outputs

Deliverables:
- export job flow
- WAV, MP3, and M4B output
- metadata form UI
- export manifest generation
- output validation

Exit criteria:
- a chaptered draft can be exported successfully

## Sprint 10: Alpha Hardening
Goals:
- stabilize the MVP for external testers

Deliverables:
- retry and resume behavior
- better parser error handling
- improved debug logging and debug bundle export
- sample-book test matrix
- prioritized stabilization backlog

Exit criteria:
- external users can complete the core workflow without engineering assistance

## Prioritization rules
If schedule pressure forces cuts, remove in this order:
1. advanced ambience features
2. rich comments UX
3. complex scene mood inference
4. sophisticated automated QA beyond core checks
5. M4B packaging polish

Never cut:
- import and structure
- voice assignment
- segment generation
- chapter assembly
- selective regeneration
- export

## Core risks
- parsing quality varies by manuscript quality
- local TTS latency may slow editing loops
- speaker attribution may be noisy
- production value may become gimmicky if defaults are too aggressive
- project state can become unrecoverable if manifests and job states are sloppy
