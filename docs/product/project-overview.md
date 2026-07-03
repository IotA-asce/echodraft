# Project Overview

## Product summary
`echodraft` is a local-first AI audiobook production system that turns long-form text into a patchable, chaptered, multi-voice audiobook draft. It sits between generic single-voice TTS and full studio dramatization: richer than plain narration, but still optimized for human review and correction.

The MVP targets single-machine execution on Apple Silicon and is intended to help a solo creator or a very small team import a manuscript, structure it into chapters/scenes/segments, assign voices, generate narration, patch weak lines, and export a presentable draft.

## Target users
### Primary users
- Indie authors with rights to their own manuscripts
- Creative producers experimenting with original or public-domain material
- Small publishing teams that need a first-pass audio workflow before studio polish

### Secondary users
- Accessibility-minded creators
- Educators producing licensed or public-domain dramatic readings
- Hobby or private-use creators where rights are clear

## Product principles
- Human-directed, AI-accelerated: AI creates drafts; humans keep editorial control.
- Consistency over novelty: stable voices and controllable delivery matter more than flashy variation.
- Editability is mandatory: every stage must support selective rework.
- Long-form native: chapter, scene, segment, and speaker continuity are first-class concerns.
- Rights-first design: export is gated by explicit rights acknowledgement.
- Taste over gimmicks: ambience and expressive delivery must remain restrained.

## MVP scope
The MVP includes:
- Text, Markdown, DOCX, and EPUB ingestion
- Chapter, scene, and segment structuring
- Character candidate extraction and speaker attribution assistance
- Narrator and character voice assignment
- Pronunciation overrides
- Scene direction defaults and per-segment overrides
- Segment-level TTS generation and selective regeneration
- Chapter assembly with optional light ambience
- QA issue tracking and review comments
- Export to WAV, MP3, and M4B packages
- Local project save/load and artifact persistence

## Explicit MVP exclusions
The MVP does not include:
- Fully autonomous one-click final production
- Mandatory cloud execution
- Collaborative multi-user editing
- Marketplace voice licensing
- Real-time review or co-listening
- Full publisher rights management
- Mobile apps or SaaS billing

## Long-term platform vision
The future platform expands the same core workflow into a publisher-grade system with:
- hybrid/cloud execution,
- collaboration and approvals,
- rights and audit workflows,
- multi-title continuity,
- localization,
- platform APIs,
- catalog-scale processing,
- organization/user management.

That future state is documented in [platform-evolution.md](platform-evolution.md). It must not blur MVP scope or introduce cloud-only assumptions into the local-first implementation.

## Non-negotiable constraints
- `Segment` remains the atomic editable and renderable unit.
- Segment render history is append-only.
- Audio blobs do not live in the relational database.
- Metadata belongs in the database; audio and manifests belong in filesystem or object storage.
- MVP architecture must function without cloud dependencies.
- Ambience and SFX remain subtle and subordinate to intelligibility.

## Success definition
The MVP is successful when a user can:
1. Import a manuscript.
2. Generate at least one coherent multi-voice chapter draft.
3. Patch only the problem lines instead of rerendering everything.
4. Export a chaptered audiobook draft.
5. Judge the result more immersive than generic single-voice TTS.
