# v2 Implementation Roadmap — Master Program Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to execute this plan workstream-by-workstream,
> task-by-task. Every task uses checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sequence the entire v2 target-product documentation suite
([`product-vision-v2.md`](../product/product-vision-v2.md), Phases A–E) into one
dependency-aware, ordered program of executable feature branches — turning nine design docs
into a single buildable order of work.

This plan does **not** re-specify any design; it merges the seven per-doc migration paths into
one critical-path-aware schedule. Each workstream links to its owning design doc, which remains
the source of truth for *what* and *how*. This plan owns *in what order* and *how we know a step
is done*.

## 1. Purpose & how to use this plan

- **Scope.** Implements the phased A–E roadmap in
  [`product-vision-v2.md` §8](../product/product-vision-v2.md). Phase A → workstreams W1–W4;
  Phase B → W5–W6; Phase C → W0 (quick wins, pulled forward) + W7; Phase D → W8; Phase E → W9.
- **Owning docs.** Every workstream cites the design doc that governs it. If this plan and a
  design doc disagree on *design*, the design doc wins; if they disagree on *sequence*, this
  plan wins. If either disagrees with [`AGENTS.md`](../../AGENTS.md), `AGENTS.md` wins.
- **Golden workflow (per [`CLAUDE.md`](../../CLAUDE.md)).** Every `- [ ]` task below is one
  mergeable feature branch. For each task: branch from the current target branch → implement
  only that scope → run the listed verification commands → commit (conventional message) →
  merge `--no-ff` → push. **Never commit to `main` directly.** Do not merge unverified work.
- **Progress tracking.** [`../progress-tracker.md`](../progress-tracker.md) must be updated in
  the same branch/commit that completes an item (its Maintenance Rule). This plan's workstreams
  map onto new tracker sections (e.g. "Phase A — Fast Automatic Pipeline"); do **not** retitle
  the existing G1–G20 history. This plan file is *not* the tracker — check tasks off here for
  local progress, but the tracker is the durable record.
- **Sizing.** Tasks carry a relative size (S ≈ ≤1 day, M ≈ few days, L ≈ ~1–2 weeks). **No
  calendar dates** — the program is ordered by dependency, not scheduled by date.
- **Exit criteria are measurable** and tie back to the vision-doc targets
  ([`product-vision-v2.md` §5](../product/product-vision-v2.md)).

## 2. Program overview

### 2.1 Two tracks start immediately, in parallel

The mandate's two loudest pains — "the UI is damn slow / page unresponsive" and "extraction
takes 6–7 h and rewriting it is risky" — are addressed by two independent tracks that begin at
once and share no code:

- **Track 1 — "stop the bleeding" (W0).** The UI performance quick wins from
  [`frontend-architecture.md` §Incremental Migration Plan step 1–2](../ui/frontend-architecture.md).
  Memoize `SegmentEditorCard`, scope the poll loops, introduce TanStack Query. Days-scale,
  no backend dependency, visibly kills most "page unresponsive" incidents before any rewrite.
- **Track 2 — "baseline" (W1).** The eval harness + attribution/casting baseline from
  [`extraction-pipeline-v2.md` §Migration step 1](../architecture/extraction-pipeline-v2.md).
  **Nothing in the pipeline rewrite may merge until the harness can score it against the
  current baseline.** This is the gate that makes "LLM-first without shipping wrong defaults"
  falsifiable rather than hopeful.

Everything else hangs off the orchestrator core (W2), which is the true spine of the program.

### 2.2 Dependency graph

```
 TRACK 1 (UI, no deps)          TRACK 2 (baseline, no deps)
 ┌──────────────────┐           ┌──────────────────────────┐
 │ W0 UI quick wins │           │ W1 eval baseline harness │
 └────────┬─────────┘           └────────────┬─────────────┘
          │ (feeds W7)                        │ (gates W3, W4)
          │                                   │
          │            ┌──────────────────────▼───────────────┐
          │            │ W2 orchestrator core                 │
          │            │ (DAG runner, checkpoints, inference  │
          │            │  cache, SSE bus, adaptive LLM pool)   │
          │            └───┬───────────────┬─────────────┬────┘
          │                │               │             │
          │        ┌───────▼──────┐  ┌─────▼──────┐      │ (SSE feeds W7 step 5)
          │        │ W3 extraction│  │ W5 TTS     │      │
          │        │ v2 (staged,  │  │ engine host│      │
          │        │ gated vs W1) │  │ + bake-off │      │
          │        └───┬──────┬───┘  └─────┬──────┘      │
          │            │      │            │             │
          │   ┌────────▼──┐   │      ┌─────▼──────────┐  │
          │   │W4 auto-   │   │      │W5 expressive   │  │
          │   │casting    │   │      │synth + char    │  │
          │   │(needs W3  │   │      │voices          │  │
          │   │profiles + │   └──────┴───────┬────────┘  │
          │   │voice cat.)│                  │           │
          │   └────┬──────┘         ┌────────▼─────────┐ │
          │        │                │ W6 generative    │ │
          │        │ (atmosphere    │ sound (needs W3  │ │
          │        │  profiles from │ atmosphere prof. │ │
          │        │  W3 feed W6)   │ + W2 audio-gen   │ │
          │        └───────────────►│ worker pool)     │ │
          │                         └──────────────────┘ │
          │                                               │
     ┌────▼───────────────────────────────────────────────▼────┐
     │ W7 UI overhaul (routes, virtualization, SSE adoption,     │
     │ design-system primitives, monolith retirement)            │
     └───────────────────────────┬──────────────────────────────┘
                                  │ (engine/UI split must be clean)
                          ┌───────▼────────┐
                          │ W8 desktop     │
                          │ packaging      │
                          │ (sidecar, Tauri│
                          │  bundled deps) │
                          └───────┬────────┘
                                  │ (desktop must ship first)
                          ┌───────▼────────┐
                          │ W9 mobile      │
                          │ (companion →   │
                          │  RN/Expo)      │
                          └────────────────┘
```

**Critical path:** W1 → W2 → W3 → W4 → (W7) → W8 → W9. W0 and W5/W6 run alongside; W7 cannot
retire the monolith until W8's engine/UI split contract is respected, and W9 cannot start until
W8 desktop apps ship.

### 2.3 Workstream summary

| WS | Name | Owning doc | Phase | Depends on | Size |
|---|---|---|---|---|---|
| **W0** | UI quick wins ("stop the bleeding") | [frontend-architecture](../ui/frontend-architecture.md) | C (pulled fwd) | — | S–M |
| **W1** | Eval baseline harness ("baseline") | [extraction-pipeline-v2](../architecture/extraction-pipeline-v2.md) | A | — | M |
| **W2** | Orchestrator core | [target-architecture](../architecture/target-architecture.md) | A | — (W1 recommended) | L |
| **W3** | Extraction v2 (staged, gated) | [extraction-pipeline-v2](../architecture/extraction-pipeline-v2.md) | A | W1, W2 | L |
| **W4** | Automatic casting | [automatic-casting-v2](../pipeline/casting/automatic-casting-v2.md) | A | W3 (profiles), W5 voice catalog seam | M–L |
| **W5** | Expressive TTS | [tts-engine-strategy](../pipeline/tts/tts-engine-strategy.md) | B | W2 (pools) | L |
| **W6** | Generative sound design | [generative-sound-design](../pipeline/assembly/generative-sound-design.md) | B | W3 (atmosphere profiles), W2 (audio-gen pool) | M–L |
| **W7** | UI overhaul | [frontend-architecture](../ui/frontend-architecture.md) + [design-system](../ui/design-system.md) | C | W0, W2 (SSE) | L |
| **W8** | Desktop packaging | [cross-platform-strategy](../platform/cross-platform-strategy.md) | D | W7, engine/UI split | L |
| **W9** | Mobile | [cross-platform-strategy](../platform/cross-platform-strategy.md) | E | W8 | L |

---

## 3. Workstreams

### W0 — UI quick wins ("stop the bleeding") · Track 1

**Goal.** Eliminate most "page unresponsive" incidents on the existing UI in days, with zero
backend dependency, before any rewrite. Owning doc:
[`frontend-architecture.md` §Incremental Migration Plan steps 1–3](../ui/frontend-architecture.md).

**Entry criteria.** Current `main` green. No dependency on any other workstream.

**Tasks.**

- [ ] **W0.1 — Memoize the worst re-render source.** Branch `feat/ui-memoize-segment-card`.
  Wrap `SegmentEditorCard` (`apps/web/app/components/.../SegmentEditorCard`) in `React.memo` with
  an id+revision-stable comparator; add `useCallback` to the handlers `SegmentList` passes per
  row so typing one character stops re-rendering every card in the scene. No behavior change.
  Verify: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **S**.
- [ ] **W0.2 — Introduce TanStack Query + convert the poll loops.** Branch
  `feat/ui-react-query-polling`. Add `@tanstack/react-query`, mount `QueryClientProvider` in the
  existing layout, and convert the `job`/`structureJob` polling effects
  (`apps/web/app/project-dashboard.tsx:129-166`, today's 1000 ms/500 ms `setTimeout` loops) to
  `useQuery({ refetchInterval: backoffFn })` with exponential backoff. Leave the remaining
  `useState` calls untouched — cache and God-component coexist. Add a bundle-size budget note in
  the PR. Verify: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **S–M**.
- [ ] **W0.3 — Scope the remaining poll loops + memoize hot leaves.** Branch
  `feat/ui-scope-polling-state`. Convert the remaining fixed-interval loops (import 750 ms,
  production 500 ms, kokoro-setup 750 ms, model-install 900 ms) to query-driven polling so a
  tick updates only its own subtree, not top-level state. `React.memo` on `IssueCard`,
  `VoiceProfileCard`, `CharacterBible`'s row renderer, `SegmentList`'s row renderer; `useCallback`
  on the ~30 inline handlers prop-drilled from the monolith. No behavior change, pure perf.
  Verify: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **M**.

**Exit criteria.** No full-tree re-render on a progress tick during a running job on the
existing UI; typing in a segment editor no longer re-renders the whole scene; the five
fixed-interval poll loops are replaced by query-driven polling. (Partial early realization of
[`product-vision-v2.md` §5.5 UI responsiveness](../product/product-vision-v2.md); the full 60 fps
/ 6,000-segment target is W7's exit.)

---

### W1 — Eval baseline harness ("baseline") · Track 2

**Goal.** Make extraction accuracy and flag-count measurable against a fixed golden corpus, and
capture the *current* pipeline's numbers as the immovable baseline every W3 stage must beat.
Owning doc: [`extraction-pipeline-v2.md` §Migration step 1](../architecture/extraction-pipeline-v2.md);
metrics per [`product-vision-v2.md` §5.3, §9](../product/product-vision-v2.md).

**Entry criteria.** Current `main` green. No dependency on any other workstream.

**Tasks.**

- [x] **W1.1 — Golden corpus fetch/seed script.** Branch `feat/eval-golden-corpus`. Add
  `apps/api/scripts/fetch_eval_corpus.py` that downloads public-domain fixtures (19th/20th-c.
  prose with hand-labeled speaker attributions) into git-ignored `test-assets/golden-corpus/` and
  verifies checksums; document the labeling schema (per-line true speaker: named / narrator /
  unknown).
  `test-assets/` stays git-ignored — never stage it. Verify: `uv run ruff check .`,
  `uv run mypy apps/api/src libs/db/src libs/domain-models/src`, script runs and populates the
  corpus. Size: **M**.
- [x] **W1.2 — Attribution & cast metrics module.** Branch `feat/eval-attribution-metrics`. Add
  `apps/api/src/echodraft_api/eval/metrics.py`: line-level attribution accuracy, cast
  precision/recall (discovered vs labeled, dedup correctness), and flag-count per book. Unit
  tests in `apps/api/tests/test_eval_metrics.py` on tiny inline fixtures.
  Verify: `uv run pytest apps/api/tests/test_eval_metrics.py`, `uv run ruff check .`,
  `uv run mypy apps/api/src libs/db/src libs/domain-models/src`. Size: **M**.
- [x] **W1.3 — Baseline report harness + recorded baseline.** Branch `feat/eval-baseline-report`.
  Add a harness (`apps/api/scripts/run_eval.py`) that runs the *current* `StructureService.extract`
  path over the corpus and writes a versioned JSON report (accuracy, flag counts, wall-clock) to
  `docs/analysis/eval-baselines/2026-07-07-baseline.json`, plus a short markdown summary. This
  frozen baseline is the comparison gate for every W3 stage. Verify: harness runs end-to-end on
  at least one corpus book; `uv run ruff check .`;
  `uv run mypy apps/api/src libs/db/src libs/domain-models/src`. Size: **M**.

**Exit criteria.** A single command produces a report with attribution accuracy, cast
precision/recall, flag count, and wall-clock over the golden corpus, and the current pipeline's
baseline numbers are committed. Every subsequent W3 comparison gate references this file.

---

### W2 — Orchestrator core

**Goal.** Replace the non-resumable in-process runner with a resumable, checkpointed, parallel
DAG engine with an inference cache, an SSE event bus, and an adaptive LLM worker pool — the
spine that makes the 6h57m → tens-of-minutes step change possible. Owning doc:
[`target-architecture.md` §9 Migration path steps 1–3, 6](../architecture/target-architecture.md).

**Entry criteria.** W1 harness exists (recommended, so throughput gains are measured, not
claimed). Current `main` green.

**Tasks.**

- [x] **W2.1 — Orchestrator package alongside the old runner.** Branch `feat/orchestrator-core`.
  Add `apps/api/src/echodraft_api/orchestrator/` with `Stage`, `Unit`, a work-queue, and a
  checkpoint store; new Alembic revision for `job_checkpoints`, `inference_cache`, `job_events`
  tables (`libs/db/alembic/versions/NNNN_orchestrator_tables.py` + matching model records +
  `_repair_sqlite_schema_drift` entries). Keep `jobs.py`'s `InProcessJobRunner` fully working;
  wire the orchestrator only for new code paths — **no behavior change yet.**
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy apps/api/src libs/domain-models/src libs/db/src`,
  migration upgrade check. Size: **L**.
- [x] **W2.2 — Event bus + SSE endpoint (polling stays as fallback).** Branch `feat/orchestrator-sse`.
  Implement `GET /api/v1/events` and persist `job_events`; the client adopts it later (W7 step 5),
  polling still works until removed. Verify: `uv run pytest` (new SSE test), `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.
- [x] **W2.3 — Inference cache + provider abstraction.** Branch `feat/inference-cache`. Replace
  the raw `urllib` call in `local_llm.py` with `OllamaLlmProvider.infer` fronted by the
  content-addressed `inference_cache`; preserve the fail-closed schema-validation contract
  bit-for-bit. No concurrency yet — caching + the seam only; reruns get cheaper immediately.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [x] **W2.4 — Adaptive LLM worker pool + hardware probe.** Branch `feat/adaptive-llm-pool`.
  Add `HardwareProbe` (RAM/VRAM/core detection) and an adaptively-sized `llm` worker pool
  (`P` from detected memory, per [`extraction-pipeline-v2.md` risks](../architecture/extraction-pipeline-v2.md));
  route all writes through a single writer task/queue (SQLite is single-writer) so fan-out does
  not hit the 30 s busy timeout. Verify: `uv run pytest` (concurrency + no-`database is locked`
  test), `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [x] **W2.5 — audio-gen + tts pool seams.** Branch `feat/orchestrator-pools`. Register `subprocess`,
  `tts`, and `audiogen` pools (schedulable independently of the `llm` pool) so W5/W6 have a home;
  add the VRAM-budget LRU model loader stub. Verify: `uv run pytest`, `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.

**Exit criteria.** New code paths run on the DAG with per-unit checkpoints; a restart *resumes*
a job instead of marking it FAILED; identical prompts hit the cache; SSE streams live progress
alongside working polling; the LLM pool sizes itself to detected hardware and no `database is
locked` occurs under fan-out. (Serves [`product-vision-v2.md` §6 "Job model"](../product/product-vision-v2.md).)

---

### W3 — Extraction v2 (staged, each behind a comparison gate)

**Goal.** Invert the pipeline to LLM-first-with-deterministic-verification, parallelized and
cached, holding flags under 20 and attribution ≥ 98% — **every stage gated on beating the W1
baseline before its flag flips on.** Owning doc:
[`extraction-pipeline-v2.md` §Migration steps 2–8](../architecture/extraction-pipeline-v2.md).

**Entry criteria.** W1 baseline committed; W2.1–W2.4 merged (pool + cache + checkpoints exist).

**Tasks.** Each task keeps the old path available behind a flag and adds a manifest version
field rather than breaking readers.

- [x] **W3.1 — Parallelize existing LLM loops (no accuracy change).** Branch `feat/extraction-parallelize`.
  Route v1's three sequential LLM loops (`structure.py:_refine_hierarchy`, `cast_discovery.py`,
  `speaker_attribution.py`) through the W2 pool + cache — same prompts, now concurrent + cached.
  **Gate:** W1 report shows accuracy unchanged (±noise) and wall-clock collapsed toward budget.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, `uv run scripts/run_eval.py`
  vs baseline. Size: **M**.
- [x] **W3.2 — Ingestion v2 (parallel OCR, no page cap).** Branch `feat/ingestion-v2-ocr`.
  Move the per-page OCR subprocess loop onto the `subprocess` pool; add per-page quality scoring
  and the front/back-matter classifier; remove the 150-page cap.
  **Gate:** OCR wall-clock scales with cores; no regression on the corpus.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [x] **W3.3 — Structure v2 (chunk MAP + seam REDUCE + coverage VERIFY).** Branch
  `feat/structure-v2-mapreduce`. Add the map/reduce/verify pipeline behind a feature flag;
  keep `structure_parsing.StructureCompiler` as the deterministic evidence provider and fallback.
  **Gate:** flip the flag only when the harness shows chapter/scene/segment fidelity ≥ baseline.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs baseline. Size: **L**.
- [x] **W3.4 — Cast v2 (embed clustering, not per-candidate LLM).** Branch `feat/cast-v2-clustering`.
  Replace `_llm_merge_decision` per-candidate adjudication (601 candidates → hundreds of
  sequential calls) with embedding-based clustering + per-cluster reconcile + profile synthesis.
  Keep the durable mention ledger, merge/split history, and prior-ruling gates unchanged.
  **This task must emit the character *profiles* W4 consumes.**
  **Gate:** cast precision/recall ≥ baseline; duplicate rate down.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs baseline. Size: **L**.
- [x] **W3.5 — Attribution v2 (LLM-primary, cascade as pre-pass).** Branch `feat/attribution-v2-llm-primary`.
  Invert `speaker_attribution.py`: cascade becomes the pre-pass, LLM window attribution becomes
  primary; add conversation-state, voting, and the book-level reduce pass. Retain
  one-row-per-segment, sibling propagation, and `userLocked` safety.
  **Gate:** ≥ 98% line attribution accuracy on the corpus and every line attributed to *some*
  explicit speaker. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs
  baseline. Size: **L**.
- [ ] **W3.6 — Confidence & flag model.** Branch `feat/extraction-flag-model`. Ship the three-tier
  confidence policy + grouped review tasks; retire the per-segment `structure_parser_warnings`
  firehose (2,453 + 731 in a real run) in favor of aggregated `issues`; calibrate thresholds on
  the harness. **Gate:** < 20 optional flags/book, 0 required steps.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs baseline. Size: **M**.
- [ ] **W3.7 — Direction v2 + progressive delivery.** Branch `feat/direction-v2-progressive`.
  Ship direction inference on the window framework and enable progressive chapter streaming
  (chapters flow to mastering as upstream stages complete) via the W2 scheduler's chapter-flow
  priority. **Gate:** first listenable chapter ≤ 10 min on mid-tier hardware.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **M–L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase A exit](../product/product-vision-v2.md)).**
A 500-page book is understood in **≤ 45 min** on mid-tier hardware; **< 20 optional flags, 0
required steps**; first listenable chapter **≤ 10 min**; jobs resume after restart; existing
audio/QA targets unchanged; every stage's W1 gate passed and recorded.

---

### W4 — Automatic casting

**Goal.** Fully automatic cast + narrator voice assignment from character traits and a real
voice catalog; manual override optional and never silently clobbered. Owning doc:
[`automatic-casting-v2.md` §Migration path](../pipeline/casting/automatic-casting-v2.md).

**Entry criteria.** W3.4 emits character profiles/traits; the voice-catalog metadata seam from
W5.4 (voice identity records) exists — or W4.1 lands its own minimal catalog table first.

**Tasks.**

- [ ] **W4.1 — Voice catalog + one-time audition backfill.** Branch `feat/voice-catalog`.
  Add `voice_catalog_entries` (+ migration + repair entry) with real gender/age/register/timbre/
  language metadata; a one-time audition job backfills it against the installed engine (Kokoro
  today), replacing `_voice_facets()`'s guessed output with measured data. Keep
  `VoiceProfile.facets`'s `list[str]` API shape so today's suggestion UI keeps working unmodified.
  Onboard the DSP feature-extraction library (librosa-equivalent) through Model Center — never
  assume preinstalled. Verify: `uv run pytest`, migration check, `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.
- [ ] **W4.2 — Narrator selection (runs first, always).** Branch `feat/casting-narrator-selection`.
  Implement Step 0 narrator selection from POV detection + the pronoun-ratio sanity check.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **S–M**.
- [ ] **W4.3 — Scoring + constraint-solving assignment.** Branch `feat/casting-solver`. Add
  `casting_decisions` (+ migration + repair entry) and the `derive_casting_spec` → `score` →
  constraint-solving assign services; walk-on/min-dialogue floor defaults a character to the
  narrator; record `catalogVersion` per decision. Ship behind `auto_cast_enabled` (default
  `true` for new projects). Verify: `uv run pytest`, migration check, `uv run ruff check .`,
  `uv run mypy ...`. Size: **L**.
- [ ] **W4.4 — Auto-chain + override model + backward compat.** Branch `feat/casting-autochain`.
  Auto-chain `casting.auto-run` after Character Bible + attribution stabilize (mirroring cast
  discovery's existing auto-chain); treat any `character_voice_assignments` row with no
  `casting_decision_id` as `user_locked = true` on first auto-cast (existing hand-cast projects
  untouched unless the user opts into re-cast); keep the ranked-alternatives view as the edit
  surface. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, and (if the cast
  UI is touched) `npm run web:lint`, `npm run web:typecheck`. Size: **M**.

**Exit criteria (ties to [`product-vision-v2.md` §5.3](../product/product-vision-v2.md)).** Every
speaking character and the narrator get a voice with zero user clicks; a character's voice is
identical across the whole book (voice-bible enforcement); narrator sits apart from the cast;
override is optional and a prior human decision is never overwritten silently.

---

### W5 — Expressive TTS

**Goal.** Make `DirectionProfile` emotion/whisper/intensity *audible in the render* (not
metadata-only), synthesize distinct new voices, tier engines per hardware, and render in
parallel. Owning doc:
[`tts-engine-strategy.md` §11 Migration](../pipeline/tts/tts-engine-strategy.md).

**Entry criteria.** W2 pools exist (`tts` pool, VRAM LRU loader). Direction metadata is reliably
produced (W3.7) before the emotion mappings can be validated end-to-end.

**Tasks.**

- [ ] **W5.1 — Engine host (generalize the resident worker).** Branch `feat/tts-engine-host`.
  Generalize `tts_worker.py`'s single-lock resident worker into a device-aware `EngineHost`
  supporting N workers on the `tts` pool; existing Kokoro/Piper/XTTS/Mock adapters keep working
  unchanged as Tier-A providers; fix the XTTS `gpu=False` hardcode behind the hardware probe.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **W5.2 — Direction compiler (Kokoro/Piper mappings first).** Branch `feat/direction-compiler`.
  Land `compile_direction` with today's honest pace+pauses mappings only, preserving the
  `direction_support`/`unsupportedDirection`/`effectiveDirection` contract bit-for-bit — plumbing
  ships before any new model. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`.
  Size: **M**.
- [ ] **W5.3 — Tier-S bake-off execution + selection.** Branch `feat/tts-bakeoff`. Run the §10
  bake-off (candidates incl. Orpheus-3B / Chatterbox / Zonos) against R10 (expressiveness) + R13
  (license) hard gates on our hardware; record results in
  `docs/pipeline/tts/bakeoff-results.md`. This task *selects*; it does not integrate.
  Verify: bake-off harness runs; `uv run ruff check .`. Size: **L**.
- [ ] **W5.4 — Tier-S integration + voice identity records.** Branch `feat/tts-tier-s`. Add the
  selected engine's Model Center catalog entry + adapter; extend `VoiceProfileRecord` with
  metadata columns + on-disk artifact paths (migration + repair entry) — the seam W4.1 reads;
  wire its real `direction_support` only for controls that passed the bake-off. New engines only
  *append* new render rows; existing Kokoro `render_key`s stay valid (constraint 6).
  Verify: `uv run pytest`, migration check, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **W5.5 — Emotion-aware direction mappings + ASR-gated retry.** Branch `feat/direction-expressive`.
  Extend `compile_direction` to map emotion/intensity/whisper onto the Tier-S engine's controls,
  bible-capped; add §7.5 ASR-gated retry + sentence chunking with Tier-A deterministic fallback
  for hallucination. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [ ] **W5.6 — New-voice synthesis / character voice cloning.** Branch `feat/character-voice-synth`.
  Wire new-voice synthesis/cloning with consent/license checks (`consentRecordId`/`license`
  verified before a cloned voice is ever offered by auto-cast); persist embeddings/reference clips
  for reproducibility. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase B exit, §5.4](../product/product-vision-v2.md)).**
Directed emotion is *audible* in a blind A/B against metadata-only renders on B4 scenes;
distinct new voices synthesize with consent tracked; render throughput on the `tts` pool keeps
play-ahead from stalling (§5.5); honesty about the local acting ceiling preserved.

---

### W6 — Generative sound design

**Goal.** AI-generated ambience/music/SFX derived from scene metadata and auto-placed, tastefully
ducked — not user-uploaded. Owning doc:
[`generative-sound-design.md` §Migration path](../pipeline/assembly/generative-sound-design.md).

**Entry criteria.** W3 emits atmosphere-profile-capable scene metadata; W2.5 audio-gen pool +
shared cache exist. Ships Tier 0 first (no model dependency).

**Tasks.**

- [ ] **W6.1 — Tier 0: procedural DSP + bundled CC0 bank.** Branch `feat/sound-tier0`. Ship
  procedural DSP ambience + a bundled CC0 sound bank — no model dependency, immediately satisfies
  "not user-uploaded" for common ambience. Verify: `uv run pytest`, `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.
- [ ] **W6.2 — Atmosphere-profile extraction (additive, optional, non-blocking).** Branch
  `feat/atmosphere-profiles`. Add atmosphere-profile extraction as an optional structure-extraction
  sub-step behind a flag; a failed/low-confidence call degrades to "no ambience for this scene,"
  never blocks structure extraction (mirrors the existing LLM-failure-creates-warning convention).
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [ ] **W6.3 — Deterministic sound planner + automatic cue placement.** Branch `feat/sound-planner`.
  Add the planner + auto cue placement writing to existing `AmbienceCueRecord`/`AmbienceAssetRecord`
  via new purely-additive columns (migration + repair entry); manual upload/manual-cue paths
  untouched as the override; never overwrite a `user_locked` cue. Verify: `uv run pytest`,
  migration check, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [ ] **W6.4 — Tier 1 generative (Stable Audio Open) via Model Center.** Branch `feat/sound-tier1`.
  Add the Model Center catalog entry behind explicit consent; stand up generation on the W2.5
  audio-gen worker pool + shared cache (intra-install cache, not cross-machine byte-identical);
  spectral-flatness QA check for voice/melody leakage; per-asset `model`/`license_note` provenance.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase B exit](../product/product-vision-v2.md)).**
Generated sound design passes the "supports, never masks" taste check on benchmark scenes (mixing
discipline enforced by measurement); it is auto-placed from scene metadata with no upload; Tier 0
works CPU-only; NC-model outputs are labeled and gated behind an explicit toggle. (Tier 2/3 are
deferred — see §6.)

---

### W7 — UI overhaul

**Goal.** Monochrome minimal design system + full frontend re-architecture: real routes,
virtualization, SSE-pushed progress, monolith retirement. Owning docs:
[`frontend-architecture.md` §Migration steps 3–7](../ui/frontend-architecture.md),
[`design-system.md`](../ui/design-system.md).

**Entry criteria.** W0 merged; W2.2 SSE endpoint live (for step W7.4).

**Tasks.**

- [ ] **W7.1 — Design tokens + primitives.** Branch `feat/design-system-primitives`. Build
  `apps/web/app/design-system/` — monochrome black/white tokens, thin type + spacing scales,
  motion spec, and primitives (Button, Select, Range, Modal/Drawer/Toast) replacing raw
  `<select>`/`<input type=range>`/`<details>` browser chrome. Verify: `npm run web:lint`,
  `npm run web:typecheck`, `npm run web:test:smoke`. Size: **L**.
- [ ] **W7.2 — Virtualize the two worst offenders in place.** Branch `feat/ui-virtualization`.
  Drop `@tanstack/react-virtual` into `SegmentList` and `ChapterTimeline`/`ChapterTranscriptReview`
  while still inside the monolith on the full in-memory array (upgraded to paged fetches later).
  Verify: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`. Size: **M**.
- [ ] **W7.3 — Extract routes one screen at a time (heaviest first).** Branch series
  `feat/route-produce`, `feat/route-structure`, `feat/route-cast`, `feat/route-review`,
  `feat/route-export-misc`. Each: create `apps/web/app/(app)/projects/[projectId]/...`, build
  `features/<name>/` hooks against TanStack Query (no God-component props), leave the monolith
  serving the not-yet-migrated sections. Order: produce → structure → cast → review → export/
  manuscript/settings/projects. Update `apps/web/tests/foundations.spec.ts` navigation
  incrementally. Verify each: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **L** (five branches).
- [ ] **W7.4 — Adopt the SSE event stream.** Branch `feat/ui-sse-adoption`. Add
  `useProjectEventStream` reading `GET /api/v1/events`; keep the W0 polling-with-backoff path
  wired but dormant (`enabled: !connected`) as the degraded-mode fallback; one `getApiBase()`
  source of truth for `fetch` and `EventSource`. Verify: `npm run web:lint`,
  `npm run web:typecheck`, `npm run web:test:smoke`. Size: **M**.
- [ ] **W7.5 — Retire the monolith + design-system pass.** Branch `feat/ui-retire-monolith`.
  Once every section has a route, delete `project-dashboard.tsx`, the `app/page.tsx` single-route
  shell, and `app/lib/workflow.ts`'s step machine (replaced by route-driven nav + an Overview
  "next best action" chip); swap remaining ad-hoc CSS for design-system primitives; add the
  `no-restricted-imports` lint rule for `fs`/`net`/`child_process`/`node:*` under `apps/web/app/**`
  to keep the pure-client-SPA invariant (W8 depends on it). Verify: `npm run web:lint`,
  `npm run web:typecheck`, `npm run web:test:smoke`. Size: **M–L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase C exit](../product/product-vision-v2.md)).**
No "page unresponsive" on a 500-page / 6,000-segment book; sustained 60 fps during a running job;
no full-tree re-render on progress ticks; the zero-touch happy path is reachable with one drop +
one export; app is a pure client SPA (static-export compatible) with a runtime-overridable API base.

---

### W8 — Desktop packaging

**Goal.** One self-contained, signed installer per desktop OS embedding the engine, with all
dependencies bundled and models auto-downloaded/verified/updated. Owning doc:
[`cross-platform-strategy.md` §3, §5, §8, §10 phasing Stages 1–3](../platform/cross-platform-strategy.md).

**Entry criteria.** W7 stable; the engine runs headless behind a stable local API; the pure-client
SPA + runtime-overridable API base invariants (W7.5) hold.

**Tasks.**

- [ ] **W8.1 — Dependency self-containment inside the dev workflow.** Branch `feat/bundled-deps`.
  Replace each system-tool call site with its bundled equivalent — pypdfium2 (poppler),
  RapidOCR (tesseract), bundled FFmpeg (LGPL, audited), `llama-cpp-python` (Ollama), bundled
  whisper.cpp — still running via `uv run`/`npm run dev` to validate each in isolation.
  Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **W8.2 — Model Center v2 download manager.** Branch `feat/model-center-v2`. Evolve Model
  Center into the per-platform download manager: verify, resume, and communicate multi-GB
  first-run downloads; on-demand model fetch with clear UX for the "your book needs a 2 GB
  download" moment. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`,
  `npm run web:lint`/`typecheck` if UI touched. Size: **L**.
- [ ] **W8.3 — Engine sidecar freeze + Tauri shell (macOS first).** Branch `feat/tauri-shell-macos`.
  Freeze the FastAPI engine as a sidecar with a stable lifecycle; wrap the static-exported UI
  (`next build` `output: "export"`) + engine in Tauri for macOS as a full sidecar-lifecycle smoke
  test. Verify: static export builds; app launches, completes a zero-touch book; smoke test green.
  Size: **L**.
- [ ] **W8.4 — Full desktop matrix + signed/notarized installers + auto-update.** Branch series
  `feat/desktop-windows`, `feat/desktop-linux`, `feat/desktop-signing`. Windows/macOS/Linux
  signed + notarized installers; auto-update wired. Verify: installer builds per OS; fresh-machine
  install completes a zero-touch book with no manual dependency install; offline works. Size: **L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase D exit](../product/product-vision-v2.md)).**
A non-technical user installs one artifact per OS and completes a zero-touch book with **no manual
dependency install**; models download/verify/update automatically; offline works.

---

### W9 — Mobile

**Goal.** The same product on Android and iOS from the shared engine — companion mode first,
then a native minimal UI, on-device tier as an opt-in stretch. Owning doc:
[`cross-platform-strategy.md` §6, §10 phasing Stages 4–5](../platform/cross-platform-strategy.md).

**Entry criteria.** W8 desktop apps shipping; engine footprint fits a mobile tier.

**Tasks.**

- [ ] **W9.1 — Companion mode (LAN pairing to a desktop engine).** Branch `feat/mobile-companion`.
  Phone plays back / lightly edits a book produced on a desktop engine over LAN; mDNS/Bonjour
  discovery **with a manual-IP / QR-code fallback from day one**. Verify: phone plays a
  desktop-produced book; QR pairing works when mDNS fails. Size: **L**.
- [ ] **W9.2 — RN/Expo app (M0/M1 tiers, mobile-native minimal UI).** Branch `feat/mobile-rn-app`.
  React Native/Expo app (not Tauri mobile) shipping the M0/M1 hardware tiers with the monochrome
  minimal design system adapted for touch; store packaging. Verify: app builds for both stores;
  responsive/touch layout passes. Size: **L**.
- [ ] **W9.3 — On-device tier (stretch, opt-in).** Branch `feat/mobile-on-device`. The M2 tier
  (quantized on-device LLM/TTS) for flagship devices — gated on W9.2 stability and on validating
  real on-device model size/performance, **not committed on paper.** Verify: on-device run
  completes within the mobile time budget on a target flagship. Size: **L**.

**Exit criteria (ties to [`product-vision-v2.md` Phase E exit](../product/product-vision-v2.md)).**
A book completes on a current mid-range phone within the defined mobile time budget; the same
zero-touch default + on-demand editing hold; no mandatory cloud.

---

## 4. Cross-workstream integration checkpoints

Named milestones where tracks converge, each with an acceptance test that must pass before the
program treats the milestone as reached.

| Milestone | Converges | Meaning | Acceptance test |
|---|---|---|---|
| **M1 — Sub-hour extraction ≥ baseline** | W1 + W2 + W3 | First sub-hour 500-page extraction at or above baseline accuracy | On the golden corpus, `run_eval.py` reports wall-clock **≤ 45 min** (mid-tier), attribution **≥ 98%**, cast precision/recall ≥ baseline, **< 20 flags**; a killed-and-restarted job **resumes** rather than restarts. |
| **M2 — Zero-touch book** | W3 + W4 + W5 + W6 | No required steps from upload to export | Drop a rights-cleared 500-page book; with **zero clicks** beyond drop + rights-ack + export, produce a mastered, chapter-marked M4B: cast + narrator auto-assigned, direction *audible*, ambience auto-placed, first listenable chapter **≤ 10 min**, all flags optional. |
| **M3 — First signed desktop installer** | W7 + W8 | A non-technical user installs and runs, no manual deps | On a clean VM per OS, install one signed artifact, launch offline, complete a zero-touch book end-to-end with **no manual dependency install**; models auto-download/verify. |
| **M4 — First phone playback of a desktop-produced book** | W8 + W9 | Companion mode works across the LAN | A desktop-produced book plays on a current mid-range phone via companion mode; pairing succeeds via QR fallback when mDNS fails; a segment edit on the phone re-renders only that segment. |

---

## 5. Risk register

| # | Risk | Workstream | Mitigation | Early-warning signal |
|---|---|---|---|---|
| R1 | **Local-LLM throughput is the hard ceiling** — parallelism can't beat a slow model | W2, W3 | LLM-first *fewer, better* calls (not just parallel), adaptive pool sizing, aggressive prompt caching | W1 wall-clock stays > 45 min after W3.1 parallelization lands |
| R2 | **Confidence gating miscalibrated** — flags balloon or wrong defaults ship silently | W3.6 | Gate every stage on the W1 harness; three-tier policy calibrated on the corpus, not assumed | Harness flag count > 20 or attribution < 98% on any corpus book |
| R3 | **TTS bake-off inconclusive** — no engine passes R10 + R13 on our hardware | W5.3 | Chatterbox/Zonos smaller fallbacks, quantized builds evaluated, honest local-ceiling + optional premium tier | No candidate clears both hard gates after the bake-off matrix runs |
| R4 | **Licensing gaps** — NC model outputs, XTTS CPML, unbundled codec, cloned-voice consent | W5, W6, W8 | R13 hard gate; treat NC output as NC-restricted; per-asset provenance; dedicated dependency-license ledger before commercial release | Any bundled binary or model lacks an audited license row |
| R5 | **SQLite write contention under parallel writers** — checkpoint/event floods hit the 30 s busy timeout | W2 | WAL (on), batch checkpoint writes, single-writer task/queue (pools are readers) | Any `database is locked` in the W2.4 concurrency test |
| R6 | **Scope creep in the UI rewrite** — route extraction never converges, monolith lingers | W7 | Strict heaviest-first route order; smoke test green after every step; monolith retired only when all routes exist | `project-dashboard.tsx` still imported after all routes shipped |
| R7 | **Model download sizes** — desktop core ≈ 1 GB+, mobile far less tolerant | W8, W9 | Mandatory on-demand download with verify/resume; dedicated download-UX; mobile ships M0/M1 first | First-run download exceeds tier budget or lacks resume |
| R8 | **Provisional-then-reconcile churn** — progressive playback forces later re-render waves | W3.7, W4 | Reconcile incrementally, cap re-render batch size, prefer minimal-reassignment voice maps | Re-render count per reconcile spikes on cross-chapter-alias books |
| R9 | **Memory pressure with 3 model families resident** (LLM + TTS + audiogen) | W2, W5, W6 | VRAM-budget LRU loader; serialize `audiogen` behind `tts`; low-memory tier drops pool size | OOM or swap thrash on a mid-tier machine during M2 |
| R10 | **iOS on-device LLM feasibility unproven** — memory/jetsam limits | W9.3 | Companion mode + M0/M1 tiers ship first; M2 gated on real prototyping, not paper | On-device prototype exceeds iOS memory-pressure limits |
| R11 | **Generative-audio taste** — score/SFX becomes theatrical or masks dialogue | W6 | "Supports, never masks" enforced by measurement (spectral flatness, ducking discipline), one-click mute/regenerate | Flatness/QA check fails on benchmark scenes |
| R12 | **Calibration transfer** — thresholds fit on public-domain prose don't generalize | W1, W3 | Broaden fixture corpus; consider per-genre calibration; keep thresholds tunable | Accuracy drops sharply on contemporary/genre fixtures |

---

## 6. Explicitly deferred (defensible program boundary)

Drawn from the non-goals of the v2 docs. These are **out of scope for this program**, not
trade-offs to negotiate mid-flight:

- **Mandatory cloud, of any kind.** Cloud stays an *optional* opt-in quality tier only; nothing
  breaks offline. ([`product-vision-v2.md` §7](../product/product-vision-v2.md))
- **Multi-user, collaboration, org accounts, billing, catalog-scale worker fleets, cross-title
  series continuity.** Publisher/Studio modes remain the post-MVP path in
  [`platform-evolution.md`](../product/platform-evolution.md) and must not pull cloud-only or
  multi-user assumptions into the local-first core.
- **DRM** — neither applied to output nor stripped from inputs; DRM-protected files are simply
  unsupported.
- **"Convert anything you can download."** Rights-acknowledgement stays the single permitted
  affirmative gate; no scraping, no access-control circumvention.
- **Tier 2/3 generative-audio models** — ship only as clearly-labeled experimental /
  non-commercial-flagged catalog entries behind an explicit toggle, never default.
  ([`generative-sound-design.md` §Migration step 5](../pipeline/assembly/generative-sound-design.md))
- **A full Rust engine rewrite.** If embedded-CPython startup/footprint becomes an unfixable
  user-facing problem post-launch, the response is an isolated Rust hot path (audio DSP the first
  candidate), not reopening the engine.
  ([`cross-platform-strategy.md` §10](../platform/cross-platform-strategy.md))
- **Tauri mobile.** Mobile uses React Native/Expo; revisit only if Tauri mobile matures.
- **Word-level forced-alignment SFX anchoring** — SFX time-anchoring stays heuristic until a
  future ASR-alignment pass adds per-word timestamps (open dependency, not this program's work).
- **Collapsing chapter/scene/segment into opaque one-shot batch jobs** — even for speed. Zero-touch
  changes the *default*, never the *granularity*; the segment stays the atomic editable/renderable
  unit, history stays append-only, and no audio blob ever enters the DB.

---

## Post-program verification

After each phase (A→W1–W4, B→W5–W6, C→W7, D→W8, E→W9) completes, run the full verification battery
from a clean `main` checkout, confirm the phase's exit criteria against
[`product-vision-v2.md` §8](../product/product-vision-v2.md), update
[`../progress-tracker.md`](../progress-tracker.md), and dispatch a whole-phase code review over the
merge range. The program is "done" per
[`product-vision-v2.md` §9 definition of done](../product/product-vision-v2.md): a solo listener
drops any rights-cleared 500-page book on any of the five platforms and gets a finished, mastered,
chapter-marked M4B in tens of minutes having pressed exactly two controls.
