# AI Audiobook Studio Docs

This directory is the working documentation set for `echodraft`, a local-first AI audiobook production system. It translates the raw PRD and engineering source material into a repo-first document set for implementation.

## Source mapping
- Product source: `../ai_audiobook_studio_prds.md`
- Engineering source: `../ai_audiobook_studio_engineering_pack.md`
- Repo operating constraints: `../AGENTS.md`

The source files above remain raw reference inputs. The documents in this directory are the implementation-facing source of truth.

## Core principles
- Local-first by default. MVP workflows must run without mandatory cloud services.
- Segment-first architecture. `Segment` is the atomic editable and renderable unit.
- Manifest-driven pipeline. Every major stage reads and writes structured manifests.
- Patch-oriented workflow. Regenerate only the affected scope and preserve render history.
- Tasteful production. Ambience and expressive delivery are intentionally conservative.

## Reading order
1. [project-overview.md](project-overview.md)
2. [mvp-product-spec.md](mvp-product-spec.md)
3. [architecture.md](architecture.md)
4. [current-pipeline-behavior.md](current-pipeline-behavior.md)
5. [model-center.md](model-center.md)
6. [pdf-ocr-ingestion.md](pdf-ocr-ingestion.md)
7. [domain-model.md](domain-model.md)
8. [db-schema.md](db-schema.md)
9. [pipeline-manifest-spec.md](pipeline-manifest-spec.md)
10. [voice-bible-spec.md](voice-bible-spec.md)
11. [tts-production-upgrade.md](tts-production-upgrade.md)
12. [sound-design.md](sound-design.md)
13. [readiness-qa.md](readiness-qa.md)
14. [review-patch-workbench.md](review-patch-workbench.md)
15. [export-polish.md](export-polish.md)
16. [qa-rulebook.md](qa-rulebook.md)
17. [api-spec.yaml](api-spec.yaml)
18. [repository-blueprint.md](repository-blueprint.md)
19. [platform-evolution.md](platform-evolution.md)

## How to use this set
- Start with the overview and MVP spec to understand scope and success criteria.
- Use current pipeline behavior to distinguish implemented alpha behavior from roadmap goals.
- Use architecture, domain, DB, manifest, voice, QA, and API docs as build contracts.
- Use `../plans/` for sequencing, sprint focus, and initial backlog ordering.
- Keep future-platform work separated from MVP execution unless a task explicitly targets the hosted evolution path.
