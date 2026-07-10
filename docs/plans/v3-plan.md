# V3 Program Plan — Prove It, Turn It On, Ship It

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to execute this program workstream-by-workstream,
> task-by-task. Every task uses checkbox (`- [ ]`) syntax for tracking. This plan is the successor
> to the [v2 implementation roadmap](v2-implementation-roadmap.md); that roadmap's
> workstreams (W0–W9) and their owning design docs remain valid and are the source of truth for
> *what* and *how*. This plan owns *what remains*, *in what order*, and *how we prove it on real
> books*.

## 1. Purpose & premise

V2 built the automatic engine. On **one developer machine**, **behind default-OFF flags**, against
**one synthetic 7-segment fixture with no live LLM**. The mechanics landed and are solid —
content-addressed inference cache, bounded parallel LLM fan-out, parallel OCR, embedding-clustered
cast, LLM-primary attribution, a direction compiler, a fail-closed TTS bake-off harness, procedural
sound DSP, virtualized lists tested at 6,000 segments. But **not one of the vision's headline
numbers has been observed on real prose**: the ≤45-min understanding target, the ≥98% attribution
target, the <20-flag target, the ≤10-min-first-chapter target, and every audio-expressiveness
claim are all *unproven*. The eval gates that were supposed to make v2 falsifiable are currently
vacuous. The zero-touch experience the vision promises is not the shipped default — it is a set of
env flags a developer flips by hand.

V3 is the program that closes that gap. Its premise in one line: **V2 wrote the engine; V3 proves
it on real books, turns it on by default, and ships apps people can install.** Three arcs:

- **Arc 1 — Prove & graduate.** Run the real-model eval on the 5-book golden corpus on real
  hardware, execute confidence calibration, and graduate each `*_v2_enabled` flag to default-on
  *only after* it clears a named gate number on real prose. Finish the two pieces of extraction
  that are still deterministic stubs (structure-v2 MAP/REDUCE, calibration). Publish wall-clock
  benchmarks. This is the arc that makes every v2 claim true or kills it.
- **Arc 2 — Perform.** Realize the expressive-audio half of the vision that was blocked on GPU
  hardware: execute the Tier-S TTS bake-off, integrate the winner, make emotion audible, implement
  direction-v2 for real (beat analysis, nonverbal spans, smoothing), actually *consume* progressive
  delivery to trigger early chapter production, and add the generative sound tier.
- **Arc 3 — Ship.** Finish the UI re-architecture (routes, SSE adoption, monolith retirement),
  package signed desktop installers with real hardware detection and bundled dependencies, and
  bring the companion mobile experience online — a book produced on a desktop, listened to on a
  phone.

Two rules carry over from [`CLAUDE.md`](../../CLAUDE.md) and [`AGENTS.md`](../../AGENTS.md) and win
every disagreement: **never commit to `main` directly** (every `- [ ]` below is one mergeable,
verified feature branch), and **the v2 design docs remain the source of truth for design**. This
plan owns sequence and proof; where it disagrees with a design doc on *design*, the doc wins; on
*sequence*, this plan wins; either loses to `AGENTS.md`. Sizing is relative (S ≈ ≤1 day, M ≈ few
days, L ≈ ~1–2 weeks) — **no calendar dates**; the program is ordered by dependency and by what a
gate can prove.

---

## 2. Entry state — honest v2 outcomes

Condensed from the three-way code review of the v2 implementation drop. This is ground truth, not
aspiration.

| State | Item |
|---|---|
| **Landed & solid** | Eval harness mechanics (corpus fetcher, metrics matching doc formulas); content-addressed inference cache (validated-only); parallelized extraction LLM loops (real bounded-pool fan-out); parallel OCR (150-page cap removed); cast-v2 embedding clustering + per-cluster LLM reconcile (flag-gated); attribution-v2 LLM-primary with cascade pre-pass + book-level reduce; direction compiler (honest pace/pause-only mappings); fail-closed TTS bake-off harness; Tier-0 procedural sound DSP; atmosphere profiles (optional/non-blocking); sound planner (ambience + SFX); design-system primitives (raw browser chrome gone); list virtualization (tested at 6,000 segments). |
| **Fixed in-wave** (assume landed when V3 starts) | Checkpoint/resume wiring (restart resumes, not FAILED); live SSE tailing; voting at temperature 0.4 with cache-key fix; casting relaxation ladder (never abort) + bounded backtracking solver; honest voice-catalog acoustics (autocorrelation pitch, FFT centroid; fabricated jitter/shimmer removed); cross-chapter atmosphere corruption fix; procedural music placement; SFX threshold/click fixes; W0.1–W0.3 (memoization, TanStack Query replacing all 5 polling loops, CharacterBible virtualization); monochrome `globals.css` completion. |
| **Debt carried into V3** | (1) structure-v2 real LLM MAP/REDUCE (currently a deterministic wrapper; coverage verifier being fixed, LLM pass unbuilt); (2) confidence calibration (thresholds hardcoded; no isotonic fit, no calibration files; [`quality-evaluation-v2.md`](../pipeline/qa/quality-evaluation-v2.md) §4 unexecuted); (3) **all eval gates vacuous** — one 7-segment synthetic fixture, no LLM; 5-book corpus never run live; ≤45-min/≥98%/<20-flag targets unproven on real prose; (4) `structure_parser_warnings` firehose not retired (grouped review_tasks layered on top); (5) every v2 stage behind a default-OFF flag — zero-touch is not the shipped default; (6) W5.3–W5.6 blocked on GPU + model downloads; (7) W6.4 generative audio (Stable Audio Open) unstarted; (8) W7.3–W7.5 (routes, SSE adoption, monolith retirement — God component ~72 useState) unstarted; (9) direction-v2 upstream is a single-pass parallel window call — no Pass-1 beat analysis, no nonverbal spans, no smoothing, no 17-emotion vocabulary; (10) progressive-delivery events emitted but nothing consumes them; (11) W8 desktop + W9 mobile unstarted; (12) hardware probe is env-var-based — no real GPU detection, device never reaches the Kokoro subprocess. |

**The one-sentence read:** the machinery works in isolation; nothing has been proven at scale, on
real prose, on real hardware, or as a default. V3 is the proof-and-ship program.

---

## 3. Arc 1 — Prove & graduate (the flag-graduation program)

*The arc that makes v2's claims true or kills them.* Nothing in this arc ships a new algorithm for
its own sake; it runs the ones already built against reality and flips them on only when the
numbers earn it. Owning docs: [`quality-evaluation-v2.md`](../pipeline/qa/quality-evaluation-v2.md),
[`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md).

### 3.1 Hardware prerequisites (stated up front, honestly)

The gates below **cannot run on the current dev machine** as they stand — the recorded eval used a
synthetic fixture precisely because a live LLM pass over 5 full books was never executed here. Arc 1
requires:

- A **mid-tier reference machine** matching the vision's definition — recent consumer laptop, 16 GB
  RAM, **no discrete GPU** — to certify the ≤45-min / ≤10-min-first-chapter targets, which are
  explicitly promised *on mid-tier hardware* ([`product-vision-v2.md` §5.1](../product/product-vision-v2.md)).
- A **live local LLM runtime** (Ollama + the pinned model) installed and warm, so the corpus runs
  hit the real inference path, not the mock.
- The **5-book golden corpus fetched and checksum-verified** into git-ignored
  `test-assets/golden-corpus/` (W1.1 script exists; it has never been run to completion on a machine
  with the LLM available).

If the reference machine is unavailable, a gate run on other hardware is **still valid as a
relative comparison** (accuracy/flags are hardware-independent) but **must not certify the
wall-clock targets** — the run's report must state the hardware tier and mark timing gates
`UNCERTIFIED` rather than passed. Honesty about hardware is a hard rule of this arc.

### 3.2 The graduation contract

Every v2 stage flag (`structure_v2_enabled`, `cast_v2_enabled` — the constrained clustering,
`attribution_v2_enabled`, `auto_cast_enabled`, atmosphere/sound flags, direction-v2) flips its
**default from OFF to ON** only when a recorded corpus run shows it clears its named gate on **real
prose across the 5-book corpus**, not on the synthetic fixture. Graduation is a deliberate,
per-flag, evidence-backed commit — never a blanket toggle.

| Flag | Graduation gate (median across 5-book corpus, real LLM) | Owning doc |
|---|---|---|
| `structure_v2_enabled` | Chapter/scene/segment fidelity ≥ recorded baseline; coverage verifier reports 100% span coverage; 0 dropped chapters | [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md) |
| `attribution_v2_enabled` | Line attribution accuracy **≥ 98%**; every line attributed to *some* explicit speaker; auto-accept precision ≥ baseline | [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md) |
| `cast_v2_enabled` | Cast precision/recall ≥ baseline; duplicate rate ↓ vs baseline; 0 merge/split errors on labeled cast | [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md) |
| `auto_cast_enabled` | Every speaking character + narrator assigned with 0 clicks; narrator distinct from cast; 0 silent overwrites of a prior human decision | [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md) |
| confidence/flag model | **< 20 optional flags/book, 0 required steps** on every corpus book, with calibrated thresholds | [`quality-evaluation-v2.md`](../pipeline/qa/quality-evaluation-v2.md) |
| direction-v2 + progressive | First listenable chapter **≤ 10 min** on mid-tier hardware | [`direction-v2.md`](../pipeline/direction/direction-v2.md) |

**Tasks.**

- [ ] **V3-A1 — Live corpus certification run.** Branch `feat/eval-live-corpus-run`. Fetch + verify
  the 5-book golden corpus; run `scripts/run_eval.py` end-to-end with the **live LLM** and every v2
  flag ON; record a versioned report to `docs/evals/YYYY-MM-DD-v3-corpus.json`
  plus a markdown summary stating hardware tier, runtime, and per-book accuracy/flags/wall-clock.
  This is the file every graduation decision below cites. Verify: harness runs to completion on all
  5 books; `uv run ruff check .`; `uv run mypy apps/api/src libs/db/src libs/domain-models/src`.
  Size: **M** (compute-bound, not code-bound).
- [ ] **V3-A2 — Structure-v2 real MAP/REDUCE.** Branch `feat/structure-v2-real-mapreduce`. Replace
  the deterministic wrapper with the real chunk-MAP + seam-REDUCE LLM pass on the W2 pool + cache,
  keeping `StructureCompiler` as the deterministic evidence provider and fallback; finish the
  coverage verifier so REDUCE cannot drop or overlap spans. **Gate:** the V3-A1 report shows
  structure fidelity ≥ baseline and 100% coverage before the flag graduates. Verify: `uv run
  pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs baseline. Size: **L**.
- [ ] **V3-A3 — Execute confidence calibration.** Branch `feat/confidence-calibration`. Execute
  [`quality-evaluation-v2.md` §4](../pipeline/qa/quality-evaluation-v2.md): fit isotonic (or
  Platt) calibration of raw model confidences against corpus ground truth; write versioned
  calibration files (per-stage) the flag model loads instead of hardcoded thresholds; regenerate on
  demand. **Gate:** calibrated thresholds hold flags < 20/book on the corpus with attribution ≥ 98%
  retained. Verify: `uv run pytest` (calibration reproducibility test), `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.
- [ ] **V3-A4 — Retire the `structure_parser_warnings` firehose.** Branch
  `feat/retire-warning-firehose`. Remove per-segment `structure_parser_warnings` emission at
  source (2,453 + 731 in a real run) now that grouped `review_tasks` exist; migrate any remaining
  reader off it; the aggregated grouped tasks become the only surface. **Gate:** a corpus run emits
  0 rows into the firehose path and < 20 grouped tasks/book. Verify: `uv run pytest`, migration
  check if schema touched, `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [ ] **V3-A5 — Per-flag graduation commits.** Branch series `feat/graduate-structure-v2`,
  `feat/graduate-attribution-v2`, `feat/graduate-cast-v2`, `feat/graduate-auto-cast`,
  `feat/graduate-flag-model`, `feat/graduate-direction-v2`. Each branch flips exactly one
  `*_v2_enabled` default from OFF to ON, cites the V3-A1 report row that clears its §3.2 gate in the
  commit message and [`../progress-tracker.md`](../progress-tracker.md), and adds a regression guard
  so the flag reverts if a later corpus run drops below the gate. A flag whose gate does **not**
  clear stays OFF and opens a debt note — graduation is earned, never assumed. Verify each:
  `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`, eval vs baseline. Size: **M** (six
  branches).
- [ ] **V3-A6 — 500-page wall-clock benchmark program.** Branch `feat/wallclock-benchmark`. Add a
  reproducible benchmark harness that times ingestion → structure → cast → attribution →
  first-listenable-chapter for a 500-page book across declared hardware tiers; publish results (with
  hardware manifest, no manuscript content) to `docs/evals/500-page-wallclock/`. **Gate:** ≤ 45
  min understanding, ≤ 10 min first chapter on the mid-tier reference machine, or an honest
  `UNCERTIFIED` + gap analysis if the reference machine is unavailable. Verify: harness runs; report
  committed; `uv run ruff check .`. Size: **M**.
- [ ] **V3-A7 — Community benchmark contribution path.** Branch `feat/community-benchmark-kit`. Turn
  V3-A6 into a one-command, telemetry-free kit a community member runs on their own hardware, which
  emits a shareable local report (hardware tier, wall-clock, flags — no manuscript content) they can
  PR into `docs/evals/500-page-wallclock/community/`. Document the contribution flow in the kit's
  README section. Verify: kit runs on a fresh checkout; produces a valid report; `uv run ruff check .`.
  Size: **M**.

**Arc 1 exit.** Every v2 extraction flag is either **graduated to default-on with a cited corpus
gate** or **explicitly held OFF with a recorded reason**; calibration files exist and are loaded;
the firehose is gone; the 500-page wall-clock is published (certified or honestly uncertified);
structure-v2 runs a real LLM pass. The zero-touch *default* is now real for the extraction half of
the pipeline.

---

## 4. Arc 2 — Perform (expressive audio, realized)

*The half of the vision blocked on GPU hardware and model downloads.* Owning docs:
[`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md),
[`direction-v2.md`](../pipeline/direction/direction-v2.md),
[`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md).

### 4.1 Hardware prerequisites

Arc 2 is **explicitly GPU-gated**. W5.3–W5.6 were deferred in v2 because no runtime was installed
and no GPU was available on the dev machine; that has not changed. This arc requires:

- A **GPU-class machine** (discrete NVIDIA GPU with ≥ 12 GB VRAM recommended, or Apple Silicon with
  ≥ 24 GB unified memory for the MPS path) to run the Tier-S bake-off candidates (Orpheus-3B /
  Chatterbox / Zonos per §10 of the TTS doc) and to certify expressive-render throughput.
- **Explicit Model Center download + license consent** for each candidate — no candidate runs
  without R13 (license) clearance recorded, per the existing fail-closed selector.
- **Blind-rating capacity** — the R10 expressiveness gate is a human blind A/B; the bake-off cannot
  self-certify. At least a small panel (3+ raters) is required.

If no GPU machine is available, Arc 2 **cannot complete** — the bake-off stays fail-closed and this
arc's flags stay OFF. That is the honest state, not a failure to route around.

**Tasks.**

- [ ] **V3-B1 — Tier-S bake-off execution.** Branch `feat/tts-bakeoff-run` (completes W5.3). On a
  GPU machine with consented model downloads, run the eight-script bake-off against R10
  (expressiveness, blind-rated) + R13 (license) hard gates; record results and the selected engine
  (or a recorded "no candidate cleared both gates") in
  [`docs/evals/2026-07-10-tts-bakeoff-results.md`](../evals/2026-07-10-tts-bakeoff-results.md). This task *selects*;
  it does not integrate. Verify: bake-off harness runs on real candidates; blind ratings recorded;
  `uv run ruff check .`. Size: **L**.
- [ ] **V3-B2 — Tier-S integration + voice identity records.** Branch `feat/tts-tier-s-integration`
  (completes W5.4). Add the selected engine's Model Center catalog entry + adapter; extend
  `VoiceProfileRecord` with metadata columns + on-disk artifact paths (migration + repair entry) —
  the seam W4.1 reads; wire `direction_support` only for controls that passed the bake-off; new
  engines only *append* render rows, existing Kokoro `render_key`s stay valid. Verify: `uv run
  pytest`, migration check, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **V3-B3 — Emotion-aware mappings + ASR-gated retry.** Branch `feat/direction-expressive`
  (completes W5.5). Extend `compile_direction` to map emotion/intensity/whisper onto the Tier-S
  engine's controls, bible-capped; add ASR-gated retry + sentence chunking with a Tier-A
  deterministic fallback for hallucination. **Gate:** directed emotion is *audible* in a blind A/B
  against metadata-only renders on B4 scenes. Verify: `uv run pytest`, `uv run ruff check .`,
  `uv run mypy ...`. Size: **M**.
- [ ] **V3-B4 — Character voice synthesis / consent-gated cloning.** Branch
  `feat/character-voice-synth` (completes W5.6). Wire new-voice synthesis/cloning with
  consent/license checks (`consentRecordId`/`license` verified before a cloned voice is ever offered
  by auto-cast); persist embeddings/reference clips for reproducibility. Verify: `uv run pytest`,
  `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **V3-B5 — Direction-v2 deep implementation (Pass-1 beat analysis).** Branch
  `feat/direction-v2-beats`. The v2 upstream is a single-pass parallel window call; implement the
  real [`direction-v2.md`](../pipeline/direction/direction-v2.md) design: a Pass-1 beat-analysis
  pass that segments scenes into emotional beats before direction inference. **Gate:** beat
  boundaries improve blind-rated delivery vs the single-pass baseline on B4 scenes. Verify: `uv run
  pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **V3-B6 — Nonverbal spans + smoothing + 17-emotion vocabulary.** Branch
  `feat/direction-v2-nonverbal`. Add nonverbal-span detection (laughter, sighs, pauses as directed
  spans), inter-segment smoothing so delivery doesn't lurch line-to-line, and the full 17-emotion
  vocabulary from the design doc (v2 shipped a reduced set). Verify: `uv run pytest`, `uv run ruff
  check .`, `uv run mypy ...`. Size: **M–L**.
- [ ] **V3-B7 — Consume progressive delivery (auto-trigger chapter production).** Branch
  `feat/progressive-consume`. Progressive-delivery events are emitted but nothing consumes them.
  Wire a consumer that, on a chapter's upstream-complete event, **auto-triggers that chapter's
  render + mastering** via the W2 scheduler's chapter-flow priority, so the earliest chapter is
  playable while the rest processes. **Gate:** measured ≤ 10-min first-listen on the reference
  machine (ties to V3-A6). Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`.
  Size: **M**.
- [ ] **V3-B8 — Tier-1 generative sound (Stable Audio Open).** Branch `feat/sound-tier1` (completes
  W6.4). Add the Model Center catalog entry behind explicit consent; stand up generation on the
  W2.5 audio-gen worker pool + shared cache; spectral-flatness QA check for voice/melody leakage;
  per-asset `model`/`license_note` provenance. NC-model outputs labeled + gated behind an explicit
  toggle. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **V3-B9 — Mixing/mastering listening program.** Branch `feat/mixing-listening-program`. A
  structured blind listening program over benchmark scenes that certifies the "supports, never
  masks" mixing discipline by measurement (spectral flatness, ducking depth, dialogue
  intelligibility) *and* by panel rating; publish the protocol + results to
  `docs/evals/listening-program/`. Verify: measurements reproducible; ratings recorded;
  `uv run ruff check .`. Size: **M**.

**Arc 2 exit.** Directed emotion is *audible* in blind A/B on B4 scenes; a Tier-S engine is selected
+ integrated (or honestly recorded as "no candidate cleared the gates"); direction-v2 runs beat
analysis + nonverbal spans + smoothing; progressive delivery auto-triggers early chapters with a
measured ≤ 10-min first-listen; the generative sound tier ships behind consent; the mixing
discipline is measured, not asserted.

---

## 5. Arc 3 — Ship (apps people install)

*The engine/UI split, packaged and signed.* Owning docs:
[`frontend-architecture.md`](../ui/frontend-architecture.md),
[`design-system.md`](../ui/design-system.md),
[`cross-platform-strategy.md`](../platform/cross-platform-strategy.md),
[`target-architecture.md`](../architecture/target-architecture.md).

### 5.1 Hardware / signing prerequisites

- **Three build hosts or a cross-build CI matrix** — macOS (for notarization; Apple requires a Mac),
  Windows (for Authenticode signing), Linux.
- **Code-signing credentials**: an Apple Developer ID + notarization credential, a Windows
  code-signing certificate. Without these, installers can be built but **not signed** — M3's
  "zero terminal steps, no Gatekeeper/SmartScreen warning" gate cannot be certified.
- **A clean VM per OS** for the fresh-machine install test.
- At least one machine with a **real NVIDIA GPU** (`nvidia-smi` present) and one **Apple Silicon**
  machine to exercise real hardware detection end-to-end.

**Tasks.**

- [ ] **V3-C1 — Real hardware detection.** Branch `feat/real-hardware-probe`. Replace the
  env-var-based `HardwareProbe` with real detection: `nvidia-smi` / NVML for NVIDIA VRAM, a `torch`
  device probe for CUDA/MPS/CPU, physical RAM/core counts; plumb the detected device all the way to
  the Kokoro (and Tier-S) subprocess so the device actually reaches the engine (today it never
  does). **Gate:** on a real GPU machine the TTS subprocess runs on CUDA/MPS, not CPU; on a
  no-GPU machine it degrades to CPU with the correct pool size. Verify: `uv run pytest`
  (probe unit tests + a device-plumbing test), `uv run ruff check .`, `uv run mypy ...`. Size: **M**.
- [ ] **V3-C2 — Extract routes (heaviest first).** Branch series `feat/route-produce`,
  `feat/route-structure`, `feat/route-cast`, `feat/route-review`, `feat/route-export-misc`
  (completes W7.3). Each: create `apps/web/app/(app)/projects/[projectId]/...`, build
  `features/<name>/` hooks against TanStack Query (no God-component props), leave the monolith
  serving not-yet-migrated sections. Order: produce → structure → cast → review → export/misc.
  Verify each: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **L** (five branches).
- [ ] **V3-C3 — Adopt the SSE event stream in the UI.** Branch `feat/ui-sse-adoption` (completes
  W7.4). Add `useProjectEventStream` reading `GET /api/v1/events`; keep the W0 polling-with-backoff
  path wired but dormant (`enabled: !connected`) as degraded-mode fallback; one `getApiBase()`
  source of truth for `fetch` and `EventSource`. Verify: `npm run web:lint`, `npm run web:typecheck`,
  `npm run web:test:smoke`. Size: **M**.
- [ ] **V3-C4 — Retire the monolith.** Branch `feat/ui-retire-monolith` (completes W7.5). Once every
  section has a route, delete `project-dashboard.tsx` (the ~72-useState God component), the
  single-route shell, and `app/lib/workflow.ts`'s step machine (replaced by route-driven nav + an
  Overview "next best action" chip); add the `no-restricted-imports` lint rule for
  `fs`/`net`/`child_process`/`node:*` under `apps/web/app/**` to keep the pure-client-SPA invariant
  (W8 depends on it). Verify: `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`.
  Size: **M–L**.
- [ ] **V3-C5 — Dependency self-containment.** Branch `feat/bundled-deps` (completes W8.1). Replace
  each system-tool call site with its bundled equivalent — pypdfium2 (poppler), RapidOCR
  (tesseract), bundled FFmpeg (LGPL, audited), `llama-cpp-python` (Ollama), bundled whisper.cpp —
  still running via `uv run`/`npm run dev` to validate each in isolation. Verify: `uv run pytest`,
  `uv run ruff check .`, `uv run mypy ...`. Size: **L**.
- [ ] **V3-C6 — Model Center v2 download manager.** Branch `feat/model-center-v2` (completes W8.2).
  Evolve Model Center into the per-platform download manager: verify, resume, and communicate
  multi-GB first-run downloads; on-demand fetch with clear UX for the "your book needs a 2 GB
  download" moment. Verify: `uv run pytest`, `uv run ruff check .`, `uv run mypy ...`,
  `npm run web:lint`/`typecheck` if UI touched. Size: **L**.
- [ ] **V3-C7 — First-run experience.** Branch `feat/first-run-experience`. The vision's narrative
  walkthrough (§2.1) requires first launch to download + verify everything with no file dialogs and
  no engine setup. Build the first-run flow: detect hardware (V3-C1), fetch the right model tier via
  Model Center v2, show honest download progress, and land the user on the "Drop a book here"
  surface with zero terminal steps. Verify: fresh-profile launch reaches the drop surface;
  `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`. Size: **M**.
- [ ] **V3-C8 — Engine sidecar + Tauri shell (macOS first).** Branch `feat/tauri-shell-macos`
  (completes W8.3). Freeze the FastAPI engine as a sidecar with a stable lifecycle; wrap the
  static-exported UI (`next build` `output: "export"`) + engine in Tauri for macOS as a full
  sidecar-lifecycle smoke test. Verify: static export builds; app launches, completes a zero-touch
  book; smoke test green. Size: **L**.
- [ ] **V3-C9 — Full desktop matrix + signed/notarized installers + auto-update.** Branch series
  `feat/desktop-windows`, `feat/desktop-linux`, `feat/desktop-signing`, `feat/desktop-autoupdate`
  (completes W8.4). Windows/macOS/Linux signed + notarized installers; auto-update wired. Verify:
  installer builds per OS; fresh-VM install completes a zero-touch book with no manual dependency
  install and no Gatekeeper/SmartScreen block; offline works; auto-update applies a bumped build.
  Size: **L**.
- [ ] **V3-C10 — Mobile companion mode.** Branch `feat/mobile-companion` (starts W9.1). Phone plays
  back / lightly edits a book produced on a desktop engine over LAN; mDNS/Bonjour discovery **with a
  manual-IP / QR-code fallback from day one**. Companion mode is the *first* mobile deliverable — no
  on-device pipeline yet. Verify: phone plays a desktop-produced book; QR pairing works when mDNS
  fails; a segment edit on the phone re-renders only that segment. Size: **L**.

**Arc 3 exit.** The monolith is gone; the UI is a pure client SPA on SSE with polling fallback; real
hardware detection drives the engine device; one signed installer per desktop OS installs with zero
terminal steps and completes a zero-touch book offline; a desktop-produced book plays on a phone via
companion mode.

---

## 6. New in V3 (beyond v2 scope)

These are **not** in the v2 docs. They extend the product once the core is proven and shipped; each
must respect every §7 guardrail of [`product-vision-v2.md`](../product/product-vision-v2.md)
(no mandatory cloud, no audio blobs in the DB, append-only history, segment stays atomic). They are
sequenced **after** their arc dependency and several are candidate community workstreams (§10).

- [ ] **V3-N1 — Multilingual books & narration.** Branch `feat/multilingual`. Structure-v2 already
  detects language (G18); extend to per-passage language tagging, language-appropriate voice
  selection from the catalog, and mixed-language narration. Owning-doc extension:
  [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md) +
  [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md). Size: **L**.
- [ ] **V3-N2 — Series / cross-book voice continuity (productized).** Branch `feat/series-continuity`.
  The v2 program explicitly *deferred* cross-title continuity as post-MVP; V3 productizes it for the
  solo listener / indie author only (a reusable voice-bible export/import across books by the same
  user), **without** pulling in multi-user or cloud assumptions. Size: **M–L**.
- [ ] **V3-N3 — Voice-pack / plugin format + community sharing.** Branch `feat/voice-pack-format`. A
  documented, signed, self-contained voice-pack format (metadata + artifacts + license +
  consent record) that a user can install locally and a community member can share — the extension
  point for community-contributed voices. No central registry required (local-first). Size: **L**.
- [ ] **V3-N4 — Position sync between devices.** Branch `feat/position-sync`. Listening-experience
  feature: playback position syncs desktop ↔ phone over the same LAN companion channel as V3-C10
  (no cloud). Size: **M**.
- [ ] **V3-N5 — Telemetry-free local benchmark reports.** Branch `feat/local-benchmark-reports`.
  Productize V3-A7's kit into an in-app "Benchmark my machine" report the user can view, clear, and
  optionally share — strictly local, no manuscript content, never a condition of use (per
  [`product-vision-v2.md` §9](../product/product-vision-v2.md)). Size: **M**.
- [ ] **V3-N6 — Security / rights hardening for distribution.** Branch `feat/distribution-hardening`.
  Once installers ship to third parties: a dependency-license ledger (audited row per bundled
  binary/model), signed voice-pack verification, rights-acknowledgement gate hardened against
  bypass, and a security review of the sidecar's local API surface (bind to loopback, auth the
  companion channel). Size: **M–L**.

---

## 7. Workstream table & dependency graph

Workstreams renumber the arc tasks into dependency-ordered units. Each cites the owning v2 design
doc (still valid).

| WS | Name | Arc | Owning doc | Entry criteria | Size | Exit criteria (measurable) |
|---|---|---|---|---|---|---|
| **V3-W0** | Live corpus certification | 1 | [quality-evaluation-v2](../pipeline/qa/quality-evaluation-v2.md) | Corpus fetched; live LLM installed; reference machine or honest tier declared | M | 5-book report committed with per-book accuracy/flags/wall-clock |
| **V3-W1** | Structure-v2 real MAP/REDUCE | 1 | [extraction-pipeline-v2](../architecture/extraction-pipeline-v2.md) | V3-W0 baseline | L | Structure fidelity ≥ baseline; 100% coverage; flag graduates |
| **V3-W2** | Calibration + firehose retirement | 1 | [quality-evaluation-v2](../pipeline/qa/quality-evaluation-v2.md) | V3-W0 baseline | M | Calibration files loaded; < 20 flags/book; firehose emits 0 rows |
| **V3-W3** | Flag graduation + wall-clock benchmark | 1 | [extraction-pipeline-v2](../architecture/extraction-pipeline-v2.md) | V3-W1, V3-W2 | M | Each flag graduated w/ cited gate or held w/ reason; 500-page benchmark published |
| **V3-W4** | Tier-S bake-off + integration | 2 | [tts-engine-strategy](../pipeline/tts/tts-engine-strategy.md) | GPU machine; model consent; blind panel | L | Engine selected + integrated, or "no candidate" recorded; emotion audible in A/B |
| **V3-W5** | Direction-v2 deep + expressive mappings | 2 | [direction-v2](../pipeline/direction/direction-v2.md) | V3-W4 (Tier-S controls); V3-W3 (reliable direction metadata) | L | Beat analysis + nonverbal spans + smoothing; blind rating beats single-pass |
| **V3-W6** | Progressive consume + generative sound + listening program | 2 | [generative-sound-design](../pipeline/assembly/generative-sound-design.md) | V3-W5; W2.5 audio-gen pool | M–L | ≤ 10-min first-listen measured; Tier-1 sound behind consent; mixing measured |
| **V3-W7** | UI routes + SSE + monolith retirement | 3 | [frontend-architecture](../ui/frontend-architecture.md) | W0.1–0.3 landed; SSE endpoint live | L | Monolith deleted; pure-client SPA on SSE w/ polling fallback |
| **V3-W8** | Real hardware detection | 3 | [target-architecture](../architecture/target-architecture.md) | GPU + Apple Silicon machines | M | Device reaches TTS subprocess; correct pool size per tier |
| **V3-W9** | Desktop packaging | 3 | [cross-platform-strategy](../platform/cross-platform-strategy.md) | V3-W7, V3-W8; signing creds; per-OS build host | L | Signed installer/OS; fresh-VM zero-touch book; offline; auto-update |
| **V3-W10** | Mobile companion | 3 | [cross-platform-strategy](../platform/cross-platform-strategy.md) | V3-W9 shipping | L | Desktop-produced book plays on phone; QR fallback; segment-scoped edit |
| **V3-W11** | New-in-V3 extensions | new | vision §7 guardrails | Owning arc shipped | L | Per-feature (multilingual, series, voice-packs, sync, reports, hardening) |

### Dependency graph

```
 ARC 1 — PROVE                              ARC 3 — SHIP (UI track runs early, parallel to Arc 1/2)
 ┌───────────────────────────┐             ┌──────────────────────────────┐
 │ V3-W0 live corpus cert    │             │ V3-W7 UI routes + SSE +      │
 │ (real LLM, 5 books, HW)   │             │       monolith retirement    │
 └────────────┬──────────────┘             │ (needs W0.1–0.3 + SSE endpt) │
              │                             └──────────────┬───────────────┘
   ┌──────────┴──────────┐                                 │
   ▼                     ▼                  ┌──────────────▼──────────────┐
┌─────────────────┐  ┌──────────────────┐   │ V3-W8 real hardware probe    │
│ V3-W1 structure │  │ V3-W2 calibration│   │ (nvidia-smi/torch → device)  │
│  real MAP/REDUCE│  │  + firehose kill │   └──────────────┬───────────────┘
└────────┬────────┘  └────────┬─────────┘                  │
         └─────────┬──────────┘             ┌──────────────▼──────────────┐
                   ▼                         │ V3-W9 desktop packaging      │
        ┌──────────────────────┐            │ (Tauri, bundled deps, MC v2, │
        │ V3-W3 flag graduation│            │  signed installers,          │
        │  + 500pg wall-clock  │            │  first-run, auto-update)     │
        └──────────┬───────────┘            └──────────────┬───────────────┘
                   │ (reliable direction metadata)         │ (desktop ships first)
 ARC 2 — PERFORM   │                         ┌─────────────▼──────────────┐
 ┌─────────────────▼──────┐                  │ V3-W10 mobile companion     │
 │ V3-W4 Tier-S bake-off  │◄── GPU + consent │ (LAN pairing, QR fallback)  │
 │  + integration         │    + blind panel └─────────────────────────────┘
 └───────────┬────────────┘
             ▼                               ┌─────────────────────────────┐
 ┌────────────────────────┐                  │ V3-W11 NEW: multilingual,   │
 │ V3-W5 direction-v2 deep│                  │  series continuity, voice-  │
 │  + expressive mappings │                  │  packs, position sync,      │
 └───────────┬────────────┘                  │  local reports, hardening   │
             ▼                               │  (each after its owning arc)│
 ┌────────────────────────┐                  └─────────────────────────────┘
 │ V3-W6 progressive       │
 │ consume + gen sound     │
 │ + listening program     │
 └─────────────────────────┘
```

**Critical path:** V3-W0 → V3-W1/W2 → V3-W3 (Arc 1 gates everything downstream, because a graduated,
reliable extraction is the precondition for both expressive audio and a shippable default). Arc 2
(V3-W4 → W5 → W6) is **GPU-gated** and runs as soon as a GPU machine + blind panel exist. The UI
track (V3-W7) has no dependency on Arc 1/2 and **starts immediately** in parallel; V3-W8 → W9 → W10
follows once the UI is a clean SPA. V3-W11 features each hang off their owning arc's completion.

---

## 8. Milestones & acceptance tests

| Milestone | Converges | Meaning | Acceptance test |
|---|---|---|---|
| **V3-M1 — Flags default-on after real-corpus gates** | V3-W0 + W1 + W2 + W3 | The automatic pipeline is *on by default* because real prose earned it | On the 5-book live corpus, a fresh project with **no flags set by hand** runs structure/cast/attribution v2; the committed report shows median attribution **≥ 98%**, **< 20 flags/book**, 0 required steps; calibration files are loaded; the firehose emits 0 rows; the 500-page wall-clock is published (certified ≤ 45 min on the reference machine, or `UNCERTIFIED` with a stated tier). Any flag that did not clear its gate is recorded as held, not silently on. |
| **V3-M2 — Blind A/B prefers Echodraft expressive render** | V3-W4 + W5 + W6 | Expressive audio is real, not metadata | On B4 benchmark scenes, a blind panel (3+ raters) prefers the Tier-S emotion-aware render over the metadata-only Tier-A render at a recorded margin; direction-v2 beat/nonverbal/smoothed output beats the single-pass baseline; first listenable chapter is measured **≤ 10 min** on the reference machine; generated sound passes the "supports, never masks" measurement. (If no candidate cleared the bake-off, M2 is honestly marked blocked-on-hardware, not passed.) |
| **V3-M3 — Signed installer on all 3 desktops, zero terminal steps** | V3-W7 + W8 + W9 | A non-technical user installs and runs, no CLI, no warnings | On a clean VM per OS, install one **signed + notarized** artifact; launch with no Gatekeeper/SmartScreen block and **zero terminal steps**; first-run auto-detects hardware and downloads the right model tier; complete a zero-touch book offline; auto-update applies a bumped build. |
| **V3-M4 — Book produced on desktop, listened on phone** | V3-W9 + W10 | Companion mode works across the LAN | Produce a book end-to-end on a desktop install; pair a phone via mDNS (with QR fallback exercised); play the book on the phone; make one segment edit on the phone and confirm only that segment re-renders and only its chapter re-stitches; position syncs back to the desktop (if V3-N4 landed). |

Each milestone runs the full [`CLAUDE.md`](../../CLAUDE.md) verification battery from a clean `main`
checkout and updates [`../progress-tracker.md`](../progress-tracker.md) in the same commit range.

---

## 9. Risk register & deferrals

### Top 10 risks

| # | Risk | WS | Mitigation | Early-warning signal |
|---|---|---|---|---|
| V3-R1 | **Real-corpus gates fail** — v2's numbers don't hold on real prose; attribution < 98% or flags > 20 once the live LLM runs 5 full books | V3-W0–W3 | Gate is falsifiable by design; a flag that fails stays OFF with a recorded reason, not silently on; calibration re-fit; prompt/algorithm iteration under the same gate | First live corpus run misses a gate on ≥ 2 books |
| V3-R2 | **GPU dependence blocks Arc 2 entirely** — no GPU machine, no bake-off, no expressive audio | V3-W4–W6 | Arc 2 is explicitly hardware-gated and stays fail-closed; Tier-A honest fallback keeps the product shippable without it; document the exact hardware needed so a contributor can unblock it | No GPU host available when Arc 1 completes |
| V3-R3 | **Model licensing** — Tier-S candidates (Orpheus/Chatterbox/Zonos), NC generative-audio models, cloned-voice consent, unbundled codecs | V3-W4, W6, W9, V3-N6 | R13 hard gate; per-asset provenance ledger; NC output treated as NC-restricted + toggle-gated; consent verified before any cloned voice is offered | Any bundled binary/model lacks an audited license row |
| V3-R4 | **Code-signing / notarization friction** — Apple notarization rejects the sidecar; Windows SmartScreen reputation cold-start | V3-W9 | Notarize early on macOS (V3-C8); staple; submit for reputation ahead of release; document a signed-but-unreputed interim state honestly | Gatekeeper/SmartScreen blocks the first signed build |
| V3-R5 | **Mobile store policy** — sideloaded engine, model downloads, on-device compute may hit App Store / Play review rules | V3-W10, W9.2+ | Companion mode first (no on-device pipeline, lowest policy surface); on-device tier deferred + gated on real review feedback, not committed on paper | Store pre-review flags model-download or background-compute behavior |
| V3-R6 | **Real hardware detection breaks the engine device path** — probe misreports, device never reaches subprocess (the v2 bug) | V3-W8 | Explicit device-plumbing test on real GPU + Apple Silicon + no-GPU machines; fail closed to CPU with correct pool size | TTS subprocess runs on CPU on a machine with a working GPU |
| V3-R7 | **Monolith retirement stalls** — 72-useState God component lingers, routes never converge | V3-W7 | Strict heaviest-first route order; smoke test green after every route; monolith deleted only when all routes exist + the `no-restricted-imports` guard passes | `project-dashboard.tsx` still imported after all routes shipped |
| V3-R8 | **Community bandwidth** — hardware-diverse bake-off + benchmark contributions don't materialize | V3-W3 (A7), §10 | Make the kit one command + telemetry-free; treat contributions as bonus coverage, never a release dependency; maintainer-run reference numbers are the gate of record | Zero community benchmark PRs after the kit ships |
| V3-R9 | **Calibration doesn't generalize** — thresholds fit on public-domain corpus fail on contemporary/genre prose | V3-W2 | Broaden the corpus over time; consider per-genre calibration; keep thresholds tunable + regeneratable; ship the fit as data, not code | Accuracy drops sharply on a non-public-domain fixture |
| V3-R10 | **First-run download weight** — multi-GB model + Tier-S engine downloads overwhelm a first launch | V3-W6 (C6/C7) | Mandatory verify/resume; tiered downloads (ship a small tier, fetch bigger on demand); the "your book needs a 2 GB download" UX moment made explicit | First-run download lacks resume or exceeds the tier budget |

### Explicit deferrals (defensible V3 boundary)

Carried from the v2 program's deferrals and extended:

- **Mandatory cloud of any kind** — cloud stays optional opt-in quality tier only.
- **Multi-user, collaboration, org accounts, billing, catalog-scale fleets** — post-MVP platform
  path; V3-N2 series continuity is the *single-user* slice only.
- **DRM** — neither applied nor stripped; DRM inputs unsupported.
- **On-device mobile pipeline (M2 tier)** — deferred behind companion mode; gated on real device
  prototyping + store review, never committed on paper.
- **Word-level forced-alignment SFX anchoring** — SFX timing stays heuristic until an ASR-alignment
  pass exists.
- **Tier 2/3 generative-audio models** — experimental / NC-flagged catalog entries behind an
  explicit toggle only, never default.
- **A full Rust engine rewrite** — an isolated Rust hot path (audio DSP first) is the response if
  embedded-CPython footprint becomes a real user-facing problem; not reopening the engine.
- **Collapsing chapter/scene/segment into one-shot batch jobs** — even for speed. The segment stays
  the atomic editable/renderable unit; history stays append-only; no audio blob enters the DB.

---

## 10. V3 and the open-source community

V3 is the first program that runs after the repo went open-source (README rewrite, community files
landed). Two things make it uniquely community-friendly, and the plan treats them as first-class.

**The hardware-diverse bake-off / benchmark program is a first-class contribution path.** The
maintainer's dev machine cannot certify the wall-clock targets (no reference mid-tier machine) and
cannot run the Tier-S bake-off (no GPU). Rather than treat this as a blocker, V3 turns it into the
front door for contributors:

- **V3-A7 community benchmark kit** — a one-command, telemetry-free harness a contributor runs on
  *their* hardware to produce a shareable 500-page wall-clock report (hardware tier, timings, flag
  counts — no manuscript content) they PR into `docs/evals/500-page-wallclock/community/`. Every
  tier of hardware a contributor owns widens the certification the maintainer alone cannot produce.
- **Tier-S bake-off runs on contributor GPUs** — V3-B1 records blind ratings + license clearance;
  a contributor with a GPU + the consented models can run a bake-off pass and contribute results to
  [`bakeoff-results.md`](../evals/2026-07-10-tts-bakeoff-results.md), unblocking Arc 2 on hardware the
  maintainer lacks.

**Good-first-workstreams** (self-contained, no GPU, no signing creds, clear gate):

- **V3-A4** — retire the `structure_parser_warnings` firehose (bounded, testable, high-value).
- **V3-C2** — extract one route from the monolith (each route is an independent branch with a smoke
  test).
- **V3-N3** — voice-pack / plugin format (a clean, documented extension point built for community
  contribution).
- **V3-N5** — telemetry-free local benchmark reports (pure local UI + report generation).
- **Corpus expansion** — add labeled public-domain books to the golden corpus (widens V3-R9's
  generalization coverage; no code, just data + labels).

**Guardrails for contributions** stay the vision's §7 rules: no mandatory cloud, no telemetry as a
condition of use, no audio blobs in the DB, append-only history, segment stays atomic. Any
contributed model or voice pack must arrive with an audited license row and (for voices) a consent
record — the V3-N6 hardening work makes that check enforceable.

---

## Post-program verification

After each arc completes (Arc 1 → V3-W0–W3, Arc 2 → V3-W4–W6, Arc 3 → V3-W7–W10), run the full
[`CLAUDE.md`](../../CLAUDE.md) verification battery from a clean `main` checkout, confirm the arc's
exit criteria and its milestone acceptance test, update [`../progress-tracker.md`](../progress-tracker.md),
and dispatch a whole-arc code review over the merge range. V3 is "done" when the
[`product-vision-v2.md` §9 definition of done](../product/product-vision-v2.md) is **proven, not
asserted**: a solo listener drops any rights-cleared 500-page book into a **signed, installed app**
on any target platform, gets a listenable first chapter in minutes and a finished, mastered,
chapter-marked M4B in tens of minutes — with the automatic pipeline on **by default because a real
corpus earned it**, expressive delivery *audible* because a blind panel confirmed it, and every
number in this plan backed by a committed report rather than a hope.
