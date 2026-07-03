# AI Audiobook Studio Docs

This directory is the working documentation set for `echodraft`, a local-first AI audiobook production system. It translates the raw PRD and engineering source material into a repo-first document set for implementation.

## Source mapping
- Product source: `sources/prds.md`
- Engineering source: `sources/engineering-pack.md`
- Repo operating constraints: `../AGENTS.md` (and `../CLAUDE.md`)

The source files above remain raw reference inputs. The documents in this directory are the implementation-facing source of truth.

## Core principles
- Local-first by default. MVP workflows must run without mandatory cloud services.
- Segment-first architecture. `Segment` is the atomic editable and renderable unit.
- Manifest-driven pipeline. Every major stage reads and writes structured manifests.
- Patch-oriented workflow. Regenerate only the affected scope and preserve render history.
- Tasteful production. Ambience and expressive delivery are intentionally conservative.

## Directory map
- **`product/`** — vision, scope, and strategy: [project-overview](product/project-overview.md), [mvp-product-spec](product/mvp-product-spec.md), [platform-evolution](product/platform-evolution.md), [roadmap](product/roadmap.md)
- **`architecture/`** — system design & cross-cutting infra: [architecture](architecture/architecture.md), [current-pipeline-behavior](architecture/current-pipeline-behavior.md), [pipeline-manifest-spec](architecture/pipeline-manifest-spec.md), [repository-blueprint](architecture/repository-blueprint.md), and `local-ai/` ([model-center](architecture/local-ai/model-center.md), [local-llm-service](architecture/local-ai/local-llm-service.md))
- **`domain/`** — data model & persistence: [domain-model](domain/domain-model.md), [db-schema](domain/db-schema.md)
- **`pipeline/`** — stage-by-stage build contracts, grouped by stage:
  - `ingestion/` — [pdf-ocr-ingestion](pipeline/ingestion/pdf-ocr-ingestion.md), [clean-text-review](pipeline/ingestion/clean-text-review.md)
  - `structure/` — [structure-parser-v2](pipeline/structure/structure-parser-v2.md)
  - `casting/` — [character-bible](pipeline/casting/character-bible.md), [speaker-attribution](pipeline/casting/speaker-attribution.md), [voice-bible-spec](pipeline/casting/voice-bible-spec.md)
  - `direction/` — [direction-studio](pipeline/direction/direction-studio.md)
  - `tts/` — [tts-production-upgrade](pipeline/tts/tts-production-upgrade.md)
  - `assembly/` — [sound-design](pipeline/assembly/sound-design.md)
  - `qa/` — [qa-rulebook](pipeline/qa/qa-rulebook.md), [readiness-qa](pipeline/qa/readiness-qa.md)
  - `review/` — [review-patch-workbench](pipeline/review/review-patch-workbench.md)
  - `export/` — [export-polish](pipeline/export/export-polish.md)
- **`api/`** — [api-spec.yaml](api/api-spec.yaml)
- **`operations/`** — [alpha-operations](operations/alpha-operations.md)
- **`analysis/`** — point-in-time evaluations: [deep-analysis-report](analysis/deep-analysis-report.md) (engineering), [product-vision-analysis](analysis/product-vision-analysis.md) (capability vision), [gap-analysis](analysis/gap-analysis.md) (current vs. vision). The resulting plan lives at [product/roadmap.md](product/roadmap.md).
- **`plans/`** — dated stage-execution history (stages 0–13).
- **`sources/`** — raw, unedited PRD/engineering inputs (historical record).
- **`assets/`** — README screenshots/GIF and the capture script.

## Reading order
1. [project-overview.md](product/project-overview.md)
2. [mvp-product-spec.md](product/mvp-product-spec.md)
3. [architecture.md](architecture/architecture.md)
4. [current-pipeline-behavior.md](architecture/current-pipeline-behavior.md)
5. [model-center.md](architecture/local-ai/model-center.md)
6. [pdf-ocr-ingestion.md](pipeline/ingestion/pdf-ocr-ingestion.md)
7. [domain-model.md](domain/domain-model.md)
8. [db-schema.md](domain/db-schema.md)
9. [pipeline-manifest-spec.md](architecture/pipeline-manifest-spec.md)
10. [voice-bible-spec.md](pipeline/casting/voice-bible-spec.md)
11. [tts-production-upgrade.md](pipeline/tts/tts-production-upgrade.md)
12. [sound-design.md](pipeline/assembly/sound-design.md)
13. [readiness-qa.md](pipeline/qa/readiness-qa.md)
14. [review-patch-workbench.md](pipeline/review/review-patch-workbench.md)
15. [export-polish.md](pipeline/export/export-polish.md)
16. [qa-rulebook.md](pipeline/qa/qa-rulebook.md)
17. [api-spec.yaml](api/api-spec.yaml)
18. [repository-blueprint.md](architecture/repository-blueprint.md)
19. [platform-evolution.md](product/platform-evolution.md)

## How to use this set
- Start with the overview and MVP spec to understand scope and success criteria.
- Use current pipeline behavior to distinguish implemented alpha behavior from roadmap goals.
- Use architecture, domain, DB, manifest, voice, QA, and API docs as build contracts.
- Use `analysis/` + `product/roadmap.md` to understand the gap to a flawless product and the planned sequence to close it.
- Use `../plans/` and `plans/` for sequencing, sprint focus, and stage history.
- Keep future-platform work separated from MVP execution unless a task explicitly targets the hosted evolution path.
