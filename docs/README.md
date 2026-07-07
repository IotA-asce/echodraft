# AI Audiobook Studio Docs

This directory is the working documentation set for `echodraft`, a local-first AI audiobook production system. It translates the raw PRD and engineering source material into a repo-first document set for implementation.

Before implementing roadmap or gap-analysis work, check [progress-tracker.md](progress-tracker.md). Update that tracker in the same branch and commit whenever a roadmap item is implemented, verified, deferred, or changes status.

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

## Target product (v2) documentation suite

The v2 suite is the design for the complete product: any book in, finished multi-voice
audiobook out, zero-touch by default, cross-platform, self-contained dependencies,
minimal monochrome UI. It documents the target state; the docs listed under the
directory map below describe the current implementation and remain the build contracts
until v2 work lands.

Read the v2 suite in this order:
1. [product-vision-v2.md](product/product-vision-v2.md) — north-star vision, quality targets, phased roadmap
2. [target-architecture.md](architecture/target-architecture.md) — engine/UI split, checkpointed DAG orchestration, inference runtime, event push
3. [extraction-pipeline-v2.md](architecture/extraction-pipeline-v2.md) — LLM-first book understanding: parallel, cached, resumable, minimal flags
4. [direction-v2.md](pipeline/direction/direction-v2.md) — automatic performance direction: emotion, delivery, nonverbals
5. [automatic-casting-v2.md](pipeline/casting/automatic-casting-v2.md) — fully automatic narrator/character voice assignment
6. [tts-engine-strategy.md](pipeline/tts/tts-engine-strategy.md) — production-grade expressive TTS, voice synthesis, engine tiering
7. [generative-sound-design.md](pipeline/assembly/generative-sound-design.md) — AI-generated ambience/music/SFX, auto-placed
8. [review-experience-v2.md](pipeline/review/review-experience-v2.md) — listen-first review: grouped tasks, spot-fix loop
9. [quality-evaluation-v2.md](pipeline/qa/quality-evaluation-v2.md) — golden corpus, metrics, calibration, regression gates
10. [design-system.md](ui/design-system.md) — monochrome minimal design system (tokens, typography, motion, components)
11. [frontend-architecture.md](ui/frontend-architecture.md) — routes, state/data layer, performance remediation
12. [cross-platform-strategy.md](platform/cross-platform-strategy.md) — desktop/mobile packaging, self-contained dependency and model management
13. [domain-model-v2.md](domain/domain-model-v2.md) — consolidated target data model (reconciles all v2 schema deltas)
14. [api-v2-contracts.md](api/api-v2-contracts.md) — consolidated API delta: pagination, SSE events, job control, new endpoints
15. [2026-07-07-v2-implementation-roadmap.md](plans/2026-07-07-v2-implementation-roadmap.md) — master implementation plan: workstreams W0–W9, milestones, risks

## Directory map
- **`product/`** — vision, scope, and strategy: [product-vision-v2](product/product-vision-v2.md) (target product), [project-overview](product/project-overview.md), [mvp-product-spec](product/mvp-product-spec.md), [platform-evolution](product/platform-evolution.md), [quality-benchmark](product/quality-benchmark.md) (the Sunday Suspense yardstick for "flawless"), [roadmap](product/roadmap.md)
- **`architecture/`** — system design & cross-cutting infra: [target-architecture](architecture/target-architecture.md) (v2), [extraction-pipeline-v2](architecture/extraction-pipeline-v2.md) (v2), [end-to-end-workflow-architecture](architecture/end-to-end-workflow-architecture.md), [architecture](architecture/architecture.md), [current-pipeline-behavior](architecture/current-pipeline-behavior.md), [pipeline-manifest-spec](architecture/pipeline-manifest-spec.md), [repository-blueprint](architecture/repository-blueprint.md), and `local-ai/` ([model-center](architecture/local-ai/model-center.md), [local-llm-service](architecture/local-ai/local-llm-service.md))
- **`domain/`** — data model & persistence: [domain-model-v2](domain/domain-model-v2.md) (v2, consolidated schema delta), [domain-model](domain/domain-model.md), [db-schema](domain/db-schema.md)
- **`pipeline/`** — stage-by-stage build contracts, grouped by stage:
  - `ingestion/` — [pdf-ocr-ingestion](pipeline/ingestion/pdf-ocr-ingestion.md), [clean-text-review](pipeline/ingestion/clean-text-review.md)
  - `structure/` — [structure-parser-v2](pipeline/structure/structure-parser-v2.md)
  - `casting/` — [automatic-casting-v2](pipeline/casting/automatic-casting-v2.md) (v2), [character-bible](pipeline/casting/character-bible.md), [speaker-attribution](pipeline/casting/speaker-attribution.md), [voice-bible-spec](pipeline/casting/voice-bible-spec.md)
  - `direction/` — [direction-v2](pipeline/direction/direction-v2.md) (v2), [direction-studio](pipeline/direction/direction-studio.md)
  - `tts/` — [tts-engine-strategy](pipeline/tts/tts-engine-strategy.md) (v2), [tts-production-upgrade](pipeline/tts/tts-production-upgrade.md)
  - `assembly/` — [generative-sound-design](pipeline/assembly/generative-sound-design.md) (v2), [sound-design](pipeline/assembly/sound-design.md)
  - `qa/` — [quality-evaluation-v2](pipeline/qa/quality-evaluation-v2.md) (v2), [qa-rulebook](pipeline/qa/qa-rulebook.md), [readiness-qa](pipeline/qa/readiness-qa.md)
  - `review/` — [review-experience-v2](pipeline/review/review-experience-v2.md) (v2), [review-patch-workbench](pipeline/review/review-patch-workbench.md)
  - `export/` — [export-polish](pipeline/export/export-polish.md)
- **`ui/`** — target UI specs (v2): [design-system](ui/design-system.md) (monochrome tokens, typography, motion, components), [frontend-architecture](ui/frontend-architecture.md) (routes, state/data layer, performance)
- **`platform/`** — cross-platform delivery (v2): [cross-platform-strategy](platform/cross-platform-strategy.md) (desktop/mobile packaging, self-contained dependencies, model management)
- **`api/`** — [api-v2-contracts](api/api-v2-contracts.md) (v2 contract delta), [api-spec.yaml](api/api-spec.yaml)
- **`operations/`** — [alpha-operations](operations/alpha-operations.md)
- **`analysis/`** — point-in-time evaluations: [deep-analysis-report](analysis/deep-analysis-report.md) (engineering), [product-vision-analysis](analysis/product-vision-analysis.md) (capability vision), [gap-analysis](analysis/gap-analysis.md) (current vs. vision). The resulting plan lives at [product/roadmap.md](product/roadmap.md).
- **`progress-tracker.md`** — checklist of roadmap/gap implementation status. This must be updated with each completed or status-changing implementation.
- **`plans/`** — dated stage-execution history (stages 0–13) and the [v2 implementation roadmap](plans/2026-07-07-v2-implementation-roadmap.md).
- **`sources/`** — raw, unedited PRD/engineering inputs (historical record).
- **`assets/`** — README screenshots/GIF and the capture script.

## Reading order
1. [project-overview.md](product/project-overview.md)
2. [mvp-product-spec.md](product/mvp-product-spec.md)
3. [architecture.md](architecture/architecture.md)
4. [end-to-end-workflow-architecture.md](architecture/end-to-end-workflow-architecture.md)
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
20. [progress-tracker.md](progress-tracker.md)

## How to use this set
- Start with the overview and MVP spec to understand scope and success criteria.
- Use current pipeline behavior to distinguish implemented alpha behavior from roadmap goals.
- Use architecture, domain, DB, manifest, voice, QA, and API docs as build contracts.
- Use `analysis/` + `product/roadmap.md` to understand the gap to a flawless product and the planned sequence to close it. "Flawless" is defined concretely in [product/quality-benchmark.md](product/quality-benchmark.md) (the Sunday Suspense yardstick).
- Use `../plans/` and `plans/` for sequencing, sprint focus, and stage history.
- Keep future-platform work separated from MVP execution unless a task explicitly targets the hosted evolution path.
