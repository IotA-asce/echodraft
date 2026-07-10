# Product Vision v2 — Any Book → Finished Audiobook

This is the north-star vision for Echodraft's next generation: a single cross-platform
app that turns *any* book into a finished, multi-voice audiobook with near-zero manual
intervention. It is the frame the rest of the v2 documentation suite hangs off. Where this
document sets direction, the following siblings specify the how:

- Architecture: [`target-architecture.md`](../architecture/target-architecture.md)
- Extraction: [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md)
- Casting: [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md)
- TTS: [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)
- Sound design: [`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md)
- Design system: [`design-system.md`](../ui/design-system.md)
- Frontend: [`frontend-architecture.md`](../ui/frontend-architecture.md)
- Cross-platform: [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)

It builds on, and does not contradict, the current-state product docs:
[`project-overview.md`](project-overview.md), [`platform-evolution.md`](platform-evolution.md),
[`quality-benchmark.md`](quality-benchmark.md), and
[`../history/analysis/product-vision-analysis.md`](../history/analysis/product-vision-analysis.md).

---

## 1. Purpose & product thesis

**Purpose.** Define the complete, target product so that every downstream design decision —
pipeline, casting, TTS, sound, UI, packaging — can be checked against one coherent picture of
what "done" looks like.

**Thesis.** *Echodraft turns any rights-cleared book into a finished, multi-voice audiobook —
mastered, chapter-marked, and listenable — with no required manual steps, running entirely on
the user's own device across Windows, macOS, Linux, Android, and iOS, with every dependency
self-managed. The default is zero-touch: drop a file in, get a finished audiobook out. Full
editorial control is always one click away for anyone who wants it, but it is never required
to reach a good result.*

The bet is a shift in posture, not scope. Today's Echodraft is a *human-directed, AI-accelerated*
production tool where the human is expected to correct hundreds of flags. v2 keeps every one of
those editing surfaces but inverts the default: the machine now carries the run end-to-end and
only asks for a human when it genuinely cannot decide. The existing segment-first, manifest-driven,
patchable, local-first, tasteful-audio foundation is preserved intact; what changes is speed,
automation, expressive quality, and where the product runs.

---

## 2. The end-state user experience

### 2.1 Narrative walkthrough

> Maya has a 480-page EPUB she has the rights to. She opens the Echodraft app on her laptop.
> The window is nearly empty: a thin-lined black-on-white surface with a single dashed target
> that reads **"Drop a book here."** She drags the EPUB in.
>
> **Seconds 0–5.** A single line appears: *"Reading your book."* No file dialogs, no format
> questions, no engine setup — the app already downloaded and verified everything it needs on
> first launch. A slim progress rail shows the run has begun. Maya sees the title, author, and
> chapter count the moment the container is parsed.
>
> **First few minutes.** The rail fills stage by stage — *Reading → Structuring → Finding the
> cast → Assigning speakers → Casting voices → Directing → Narrating → Mixing → Mastering.* Each
> stage shows a live count (e.g. *"37 characters found, 12 with speaking parts"*) rather than a
> spinner. Nothing blocks. Maya does not click anything.
>
> **Listenable within minutes.** As soon as Chapter 1 is mastered, a **Play** control lights up
> and she can start listening while the rest of the book renders behind her. The player shows
> the current chapter, a lightweight waveform, and which voice is speaking. She listens to the
> opening while Chapters 2–20 continue processing.
>
> **If she does nothing.** The run finishes on its own. She gets one notification —
> *"Your audiobook is ready"* — and an **Export** control. She exports an M4B with chapter
> markers, cover art, and mastered loudness. Total hands-on time: dropping one file and pressing
> export.
>
> **If she wants to change something.** At any point she can open any chapter, scrub to a moment,
> and tap a line. She hears exactly that line, sees who the app cast for it and why, and can
> reassign the voice, retune the delivery, fix a pronunciation, or edit the text. She changes it;
> only that line re-renders and the chapter re-stitches. Everything she did *not* touch stays
> exactly as it was. The app never forces her into an editor to finish.

### 2.2 The "zero-touch by default, fully editable on demand" principle (precise definition)

This principle is the product's spine. It has four hard rules:

1. **A run completes with zero required human input.** From a dropped file to an exportable,
   mastered audiobook, there is **no mandatory manual step**. Structure, cast, attribution,
   casting, direction, narration, sound, and mastering all resolve automatically. Rights
   acknowledgement (a legal gate, not a production step) is the *only* affirmative action the
   product may require before export — see §7.

2. **Manual resolution is always optional and always additive.** Every ambiguity the machine
   could not decide with confidence becomes an *optional* flag (a durable `issue` or per-scope
   `warning`), never a blocking stop. The book is finishable with all flags unaddressed; the
   machine has already chosen a defensible default for each. Flags are an invitation to improve,
   not a debt to clear.

3. **Editing is segment-granular and patch-only.** Any edit — voice, direction, text,
   pronunciation, cut point — re-renders only the affected segment(s) and re-stitches only the
   affected chapter, preserving append-only render history. Editing never triggers a full rerun.
   (Preserves the current segment-first, patchable architecture.)

4. **The two modes are one product, not a toggle.** There is no "advanced mode." The finished
   audiobook and the full editing surface are the same artifact seen at two zoom levels. A user
   can go from listening to editing a single line and back without leaving a "wizard."

### 2.3 Preview-while-processing

Progressive delivery is a first-class feature, not a loading screen:

- **Streaming stages:** the pipeline is a resumable DAG (see
  [`target-architecture.md`](../architecture/target-architecture.md)); chapters flow to
  mastering as soon as their upstream stages complete, rather than all-at-once at the end.
- **Play-ahead:** the earliest finished chapter is playable while later chapters render.
- **Live counts, not spinners:** every stage reports concrete progress (segments, characters,
  chapters mastered) pushed to the UI over an event channel — never client polling (fixes the
  current 500 ms poll-loop meltdown described in [`frontend-architecture.md`](../ui/frontend-architecture.md)).

---

## 3. Product pillars (ranked)

Ranked by how directly they serve the mandate (a finished audiobook from any book, fast, on
every platform). The first five restate Echodraft's existing non-negotiable priorities; the
rest are the v2 additions.

| # | Pillar | What it means | Status |
|---|---|---|---|
| 1 | **Automatic everything** | The default path is zero-touch: structure, cast, attribution, casting, direction, sound, and mastering all resolve without the user. Human input is optional and additive only. | New posture over existing pipeline |
| 2 | **Segment-first** | The segment stays the atomic editable and renderable unit; all automation and editing operate at segment granularity. | Preserved |
| 3 | **Manifest-driven** | Every stage emits a durable manifest; runs are inspectable, resumable, and reproducible from manifests. | Preserved |
| 4 | **Patchable** | Targeted re-render always works; edits never force a full rerun; render history is append-only. | Preserved |
| 5 | **Local-first privacy** | The full pipeline runs on-device with no mandatory cloud. Cloud is only ever an *optional* quality tier the user opts into. | Preserved |
| 6 | **Tasteful audio** | Ambience, music, and expressive delivery stay subordinate to intelligibility — present, never masking the words. | Preserved |
| 7 | **Fast pipeline** | A 500-page book is understood in tens of minutes, not hours, via LLM-first-where-it-earns-it design, parallelism, caching, and confidence-gated escalation (see §5, [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md)). | New |
| 8 | **Production-grade expressive voices** | TTS that synthesizes distinct new voices and *actually renders* delivery — anger, anguish, laughter, whisper, tension — not metadata-only direction. | New |
| 9 | **Generative sound design** | Ambience, score, and SFX are AI-generated from scene metadata and auto-placed, tastefully mixed — not user-uploaded. | New |
| 10 | **Cross-platform app** | One product on Windows, macOS, Linux, Android, iOS from a shared engine. | New |
| 11 | **Self-contained dependencies** | The app downloads, verifies, and manages every model and system tool itself, per platform. No manual installs. | New (extends Model Center) |
| 12 | **Minimal monochrome UI** | Essentially two colors (black/white), thin typography, motion only where it informs. Clean, fast, not a prototype. | New |

Pillars 2–6 are load-bearing constraints inherited from
[`project-overview.md`](project-overview.md) and AGENTS.md; the v2 additions (1, 7–12) must be
achieved *without* violating them. In particular: no v2 feature may introduce a mandatory cloud
dependency, store audio blobs in the database, or replace append-only history with overwrite
semantics.

---

## 4. Personas & jobs-to-be-done

| Persona | Primary job | Success looks like | Phase |
|---|---|---|---|
| **Solo listener** | "I have a book I'm allowed to convert; I just want to listen to it well-narrated." | Drops a file, gets a mastered multi-voice audiobook, never opens an editor. | **MVP** |
| **Indie author** | "Turn my own manuscript into a distributable audiobook I can fine-tune." | Zero-touch draft in tens of minutes; then edits voices/pronunciations for their own characters; exports a retail-ready M4B. | **MVP** |
| **Small publisher / producer** | "First-pass multi-title audio before studio polish, with editorial control and rights traceability." | Batch-processes titles, reviews via ranked flags, enforces consistency across a series, exports with metadata. | **Later** (aligns with Publisher/Studio modes in [`platform-evolution.md`](platform-evolution.md)) |

Secondary/adjacent jobs — accessibility-minded creators, educators with licensed/public-domain
material, hobbyists — are served by the same MVP zero-touch path and need no bespoke mode.

**Scope discipline.** The solo listener and indie author are the MVP north star and drive every
Phase A–E decision. Publisher/producer capabilities (collaboration, approvals, org accounts,
catalog-scale worker fleets, cross-title continuity) remain post-MVP exactly as
[`platform-evolution.md`](platform-evolution.md) specifies, and must not pull cloud-only or
multi-user assumptions into the local-first core.

---

## 5. Quality bar (measurable targets)

These are the concrete definitions of "works almost flawlessly." Each is measurable locally
(see §9). Rationale numbers come from the current-state research summarized in the shared brief.

### 5.1 Speed

| Metric | Current | v2 target | Rationale |
|---|---|---|---|
| **Understanding a 500-page book** (ingestion → structure → cast → attribution, wall-clock) | ~5–7 h (a real run took **6 h 57 m**) | **≤ 30–45 min on mid-tier hardware**; ≤ 15 min on a GPU-class machine | The current cost is almost entirely *sequential* local LLM calls (~500–1500 per book, seconds each) with zero intra-job concurrency and no prompt caching. Parallelizing LLM work, caching identical prompts, and reserving the LLM for genuinely ambiguous cases (deterministic passes handle the rest) collapses this by an order of magnitude. See [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md). |
| **Time to first listenable chapter** | Not available until the whole structure job finishes | **≤ 10 min** on mid-tier hardware | Progressive delivery: Chapter 1 flows to mastering while the rest processes. This is the metric the user *feels*. |
| **PDF OCR (150-page cap today)** | Sequential (one `pdftoppm` + `tesseract` per page) | Parallel across cores; no fixed page cap | OCR is embarrassingly parallel; the cap and serialization are implementation limits, not real ones. |

Hardware tiers are defined in [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md);
"mid-tier" means a recent consumer laptop with 16 GB RAM and no discrete GPU.

### 5.2 Manual-resolution budget

| Metric | Current | v2 target |
|---|---|---|
| **Required manual steps to finish a book** | Effectively unbounded (blocking issues can gate export) | **0** — a book is always finishable untouched |
| **Optional flags surfaced per book** | Thousands (a real run produced **2,453** "no speaker attribution" + **731** "low confidence" warnings and **601** cast candidates with **435** possible duplicates) | **< 20 genuine, high-value flags per book**, all optional, each with attached evidence and a one-click action |

The reduction comes from confidence-gated automation: the machine commits a defensible default
for everything it can decide, and only escalates the handful of cases where committing would
likely be wrong. A flag must clear a "worth a human's 30 seconds" bar to appear.

### 5.3 Attribution & casting accuracy

| Metric | v2 target | Maps to |
|---|---|---|
| **Cast identification** | Every named speaker discovered, de-duplicated, and aliased; no character missed, none doubled. | Benchmark B1 |
| **Speaker attribution** | ≥ 98% of lines attributed to the correct speaker on typical prose; every line attributed to *some* explicit speaker (named / narrator / unknown), never a silent narrator default; genuine ambiguities triaged, not guessed. | Benchmark B2 |
| **Voice distinctness** | Each character instantly distinguishable; narrator sits apart from the cast; casting fits gender/age/register traits. | Benchmark B3 |
| **Casting stability** | A character's voice is identical across the entire book (voice-bible enforcement — see [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md)). | B3 |

"Correct" is measured against the [Sunday Suspense quality benchmark](quality-benchmark.md):
indistinguishable from a human multi-voice production to an ordinary listener on B1, B2, B5–B8,
and honest about the B3/B4 local-TTS acting ceiling.

### 5.4 Audio & QA standards (reuse existing)

| Metric | Target | Notes |
|---|---|---|
| **Integrated loudness** | **−19 LUFS** (±1.0 dB tolerance; ±0.5–1 LU chapter-to-chapter) | Existing mastering target; within the ACX −23…−18 window. |
| **True peak** | **≤ −3 dBTP** | Existing target via 2-pass `loudnorm` / lookahead limiter. |
| **Sample rate / depth** | 44.1 kHz / 16-bit masters | Existing assembly path. |
| **LRA** | ~11 | Existing mastering measurement. |
| **Delivery containers** | WAV (zip), MP3 ≥192 kbps + ID3 + cover, **M4B** with chapter markers + metadata + artwork (flagship) | Existing export capability. |
| **Listener-grade QA** | Every export carries a QA scorecard (LUFS/TP within tolerance, ASR word-match, no clipping/dead-air/truncation); "no automated flag" stays distinct from "listened and approved." | Existing QA model (B8). |
| **Expressive delivery** | Directed emotion (anger, anguish, laughter, whisper, tension) is *audible in the render*, not metadata-only. | New — closes the current gap where `DirectionProfile` emotion/whisper/intensity never reach any engine. Frontier of the local ceiling (B4); see [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md). |

### 5.5 Progressive delivery

- **Listenable first chapter within ≤ 10 min** (restated from §5.1 as a headline promise).
- **Play-ahead never stalls:** the player must always have the next chapter mastered before the
  current one ends, on mid-tier hardware, for books up to 500 pages.

---

## 6. What changes vs today (honest gap table)

One row per gap. "Current" is grounded in the codebase research in the shared brief; "Target" is
the v2 commitment. Detailed remediation lives in the linked sibling docs.

| Area | Current behavior | v2 target | Owner doc |
|---|---|---|---|
| **Pipeline speed** | ~6–7 h for a 500-page book; zero intra-job concurrency; every Ollama call blocking, uncached; sequential OCR/TTS. | ≤ 30–45 min; parallel DAG, prompt caching, batched inference, parallel OCR. | [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md), [`target-architecture.md`](../architecture/target-architecture.md) |
| **Manual flags** | Thousands of warnings + hundreds of cast candidates; blocking issues can gate export. | < 20 optional flags; nothing blocks finishing. | [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md) |
| **Structure/attribution method** | Deterministic-first heuristics with sequential LLM cleanup on `needs_review` rows. | LLM-first where it earns accuracy, with deterministic verification and confidence gating. | [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md) |
| **Voice assignment** | Fully manual: create profiles, `assign-voice` per character; suggestions are keyword scores the user must click. | Fully automatic cast+narrator assignment from character traits and a real voice catalog; user override optional. | [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md) |
| **Voice metadata** | `VoiceProfileRecord` has no real metadata columns; facets regex-guessed from Kokoro voice-ID prefixes. | Voice catalog with real gender/age/register/timbre/language metadata driving matching. | [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md) |
| **TTS expressiveness** | Kokoro (default), Piper, XTTS-v2; only pace + pauses reach engines; emotion/whisper/intensity are metadata-only; XTTS `gpu=False` hardcoded; one synthesis at a time (single worker lock). | Emotion/delivery-aware synthesis, new-voice synthesis/cloning, engine tiering per hardware, GPU path, parallel rendering. | [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md) |
| **Sound design** | Upload-only local WAVs; scene-scoped cues; zero generative audio. | AI-generated ambience/music/SFX derived from scene metadata and auto-placed under dialogue. | [`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md) |
| **Job model** | `InProcessJobRunner`, not resumable — restart marks RUNNING jobs FAILED; coarse phase counters. | Resumable checkpointed DAG; restart resumes; fine-grained live progress. | [`target-architecture.md`](../architecture/target-architecture.md) |
| **UI performance** | One 553-line "God component"; 5 recursive poll loops (down to 500 ms) → full-tree re-render 1–2×/sec; no virtualization; "page unresponsive." | Event-pushed progress, virtualized lists, memoized components, real routes. | [`frontend-architecture.md`](../ui/frontend-architecture.md) |
| **Visual design** | Cream/green/terracotta "craft paper" palette, serif+sans, browser-chrome controls, JSON dumps in the UI; feels like a prototype. | Monochrome black/white, thin typography, tasteful motion, real component system. | [`design-system.md`](../ui/design-system.md) |
| **Platforms** | Local dev app; single-machine Apple Silicon focus; no packaging. | Packaged apps for Windows/macOS/Linux/Android/iOS from a shared engine. | [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md) |
| **Dependencies** | Model Center handles system tools + models with explicit consent, no GPU path, no cloud path. | Fully self-managed per-platform download/verify/update of all models & tools, with GPU tiers. | [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md) |

---

## 7. Non-goals & guardrails

These are firm. A feature that requires violating one of these is out of scope, not a trade-off.

- **No mandatory cloud.** The full pipeline runs on-device. Cloud is only ever an *optional*
  quality tier the user explicitly opts into (e.g. a premium final-render pass); nothing breaks
  offline. (Local-first privacy pillar.)
- **Rights-respecting only.** The product converts material the user has the rights to. Export
  stays gated behind explicit rights acknowledgement — the single permitted affirmative gate.
  No scraping, no circumventing access controls, no "convert anything you can download."
- **No DRM ambitions.** Echodraft neither applies DRM to its output nor strips DRM from inputs.
  DRM-protected files are simply unsupported inputs.
- **No audio blobs in the database.** The relational DB holds metadata and filesystem paths only;
  all audio and manifests live on the filesystem. (Preserved constraint.)
- **No overwrite of history.** Segment and chapter render history stays append-only; edits create
  new records, never mutate old ones. (Preserved constraint.)
- **Segment stays atomic.** No collapsing chapter/scene/segment structure into opaque one-shot
  batch jobs, even in the name of speed. Zero-touch changes the *default*, not the *granularity*.
- **Automation never removes control.** Full automation must not delete or hide any editing
  surface. Every automatic decision remains inspectable, evidence-backed, and reversible.
- **Taste over spectacle.** Generative sound and expressive TTS stay subordinate to
  intelligibility; the product does not chase theatrical excess that masks the words.
- **No dark-pattern telemetry.** Telemetry is local-only and never a condition of use (see §9).
- **MVP scope discipline.** No multi-user, collaboration, org accounts, billing, or catalog-scale
  infrastructure in the MVP core; those remain the post-MVP platform path in
  [`platform-evolution.md`](platform-evolution.md).

---

## 8. Phased roadmap (vision level)

Phases are ordered by user pain per the mandate: **speed and automation first, expressive quality
second, then the UI overhaul, then desktop packaging, then mobile.** Each phase has explicit
entry and exit criteria; a phase ships only when its exit criteria are met and verified.

### Phase A — Fast, automatic pipeline
*The book finishes itself, quickly.*

- **Scope:** resumable parallel DAG orchestration; LLM-first-with-verification extraction;
  prompt caching + batched/parallel inference; parallel OCR; fully automatic cast + narrator
  casting from a real voice catalog; confidence-gated flag reduction; progressive chapter delivery.
- **Entry:** current code merged and green; target-architecture and extraction-pipeline-v2 specs
  approved.
- **Exit:** a 500-page book is understood in **≤ 45 min** on mid-tier hardware; **< 20 optional
  flags**, **0 required steps**; first listenable chapter **≤ 10 min**; casting is automatic with
  optional override; jobs resume after restart. Existing audio/QA targets (§5.4) unchanged.

### Phase B — Expressive TTS & generative sound
*It sounds produced, not synthesized.*

- **Scope:** emotion/delivery-aware synthesis so `DirectionProfile` actually renders; new-voice
  synthesis/cloning; engine tiering + GPU path + parallel rendering; AI-generated ambience/music/
  SFX derived from scene metadata and auto-placed with tasteful ducking.
- **Entry:** Phase A exit met; direction metadata is reliably produced by the pipeline.
- **Exit:** directed emotion is *audible* in blind A/B against metadata-only renders on B4 test
  scenes; generated sound design passes the "supports, never masks" taste check on the benchmark
  scenes; render throughput keeps play-ahead from stalling (§5.5). Honesty about the local acting
  ceiling preserved (per [`quality-benchmark.md`](quality-benchmark.md)).

### Phase C — Minimal monochrome UI
*Fast, clean, not a prototype.*

- **Scope:** monochrome design system (tokens, thin type, motion spec); frontend re-architecture
  (real routes, virtualized lists, memoization, event-pushed progress replacing poll loops);
  zero-touch-first IA with editing on demand.
- **Entry:** Phases A–B produce the events/streams the new UI consumes.
- **Exit:** no "page unresponsive" on a 500-page / 6,000-segment book; sustained 60 fps during a
  running job; no full-tree re-render on progress ticks; the zero-touch happy path is reachable
  with one drop + one export.

### Phase D — Desktop packaging
*One installer per desktop OS, self-contained.*

- **Scope:** packaged Windows/macOS/Linux apps embedding the engine; self-managed per-platform
  download/verify/update of all models and tools (extending Model Center); hardware tiering; update
  strategy.
- **Entry:** Phase C UI stable; engine runs headless behind a stable local API.
- **Exit:** a non-technical user installs one artifact per OS and completes a zero-touch book with
  **no manual dependency install**; models download/verify/update automatically; offline works.

### Phase E — Mobile
*The same product on Android and iOS.*

- **Scope:** Android and iOS apps from the shared engine; mobile hardware tiering (on-device where
  feasible, optional opt-in offload where not); mobile-native minimal UI; store packaging.
- **Entry:** Phase D desktop apps shipping; engine footprint fits a mobile tier.
- **Exit:** a book completes on a current mid-range phone within a defined mobile time budget (set
  in [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)); the same zero-touch
  default and on-demand editing hold; no mandatory cloud.

---

## 9. Success metrics & local measurement

All metrics are measured **on-device, local-only**. Telemetry never leaves the machine, is never a
condition of use, and stores no manuscript content — only run-level measurements the user can
inspect and clear.

| Metric | Definition | How measured locally |
|---|---|---|
| **Zero-touch completion rate** | Share of runs that reach an exportable master with 0 human edits. | Job manifests record whether any edit/override was applied before export. |
| **Time-to-finish** | Wall-clock from file drop to exportable master, per 500-page-normalized book. | Stage timestamps in the resumable-job records / manifests. |
| **Time-to-first-chapter** | Wall-clock from drop to first playable mastered chapter. | Chapter-render manifest timestamps. |
| **Flags-per-book** | Count of optional flags surfaced (should be < 20). | Count of durable `issues` + per-scope `warnings` emitted per run. |
| **Attribution accuracy** | % lines correctly attributed on a held-out fixture set. | Offline eval harness against labeled fixtures (local `test-assets`). |
| **Audio conformance** | % chapters within LUFS/TP tolerance and passing ASR word-match. | Existing QA scorecard (LUFS/TP measurement + local ASR). |
| **Patch locality** | An edit re-renders only affected segments and re-stitches only affected chapters. | Append-only render records show scope of re-render per edit. |
| **UI responsiveness** | No full-tree re-render on progress ticks; sustained frame rate during a job. | Frontend performance profiling on the benchmark book. |
| **Edit engagement (opt-in signal)** | Whether users who *want* to edit find it (distinct from those who never do). | Local-only interaction counts; used to validate the "editable on demand" promise, never to nudge. |

**Definition of "done" for the product:** a solo listener drops any rights-cleared 500-page book,
gets a listenable first chapter in minutes and a finished, mastered, chapter-marked M4B in tens of
minutes, having pressed exactly two controls (drop, export) — and an indie author, from that same
run, can retune any voice, line, or pronunciation with single-click segment-granular patches, all
on their own device, on any of the five target platforms, with every dependency the app installed
itself.

---

## 10. Risks & open questions

**Risks.**

- **LLM-first accuracy vs. speed.** Reserving the LLM for judgment while committing defensible
  defaults everywhere else is the whole speed/flag bet. If confidence gating is miscalibrated,
  either flags balloon (defeating zero-touch) or wrong defaults ship silently (defeating quality).
  Mitigation: measure attribution accuracy and flag counts against fixtures every build (§9).
- **Expressive-TTS ceiling (B4).** Per [`quality-benchmark.md`](quality-benchmark.md), fine-grained
  emotional acting is where local open TTS trails human/frontier engines. v2 must be *honest* about
  this at the point of control and offer an *optional* premium tier — not pretend the ceiling away.
- **Generative-audio taste.** Auto-generated score/SFX can easily become theatrical or mask
  dialogue. The "supports, never masks" mixing discipline must be enforced by measurement, not
  vibes.
- **Hardware variance.** "Mid-tier ≤ 45 min" and mobile budgets depend on tiering that degrades
  gracefully on weak hardware and exploits GPUs where present, without a mandatory cloud fallback.
- **Self-contained dependency weight.** Bundling/downloading multiple models per platform (and
  fitting a mobile tier) risks large install sizes and long first-run downloads; the download
  manager must verify, resume, and communicate this cleanly.
- **Scope creep from the platform vision.** Publisher/studio features must stay out of the MVP core
  (§4, §7) so they don't drag cloud-only or multi-user assumptions into local-first code.

**Open questions** (resolved in the linked sibling docs, tracked here for coherence):

- Which specific TTS model(s) deliver synthesizeable new voices *and* controllable delivery within
  the local hardware budget, and where exactly does the optional premium tier begin?
  → [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)
- What local generative-audio models are viable for ambience/music/SFX at acceptable latency, and
  how is a scene turned into a sound prompt? → [`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md)
- What is the packaging/runtime shape that lets one engine serve five platforms, and what is the
  mobile time budget? → [`cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
- What is the exact confidence model and escalation policy that holds flags under 20 without
  shipping wrong defaults? → [`extraction-pipeline-v2.md`](../architecture/extraction-pipeline-v2.md)
- How does the resumable DAG checkpoint mid-stage so a restart loses seconds, not the run?
  → [`target-architecture.md`](../architecture/target-architecture.md)
