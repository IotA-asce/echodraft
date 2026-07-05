# Echodraft — Gap Analysis

**Date:** 2026-07-03
**Baseline:** current `main` implementation + documented behavior in `docs/`.
**Target:** the "flawless product" defined in [`product-vision-analysis.md`](product-vision-analysis.md), grounded by the engineering findings in [`deep-analysis-report.md`](deep-analysis-report.md). "Flawless" is made concrete by the [Sunday Suspense quality benchmark](../product/quality-benchmark.md) — that document defines what a maturity **5** actually sounds like, dimension by dimension.
**Purpose:** measure, per capability and per cross-cutting principle, how far today's system is from the vision, and size each gap so a roadmap can sequence the work. This document intentionally does not propose the sequence — that is the roadmap's job.

---

## 1. Method & maturity rubric

Each capability and principle is scored on a 0–5 maturity scale against the vision:

| Level | Meaning |
|---|---|
| **0 — Absent** | Not implemented at all. |
| **1 — Stubbed / dishonest** | Present in name/UI/API but faked, hardcoded, or a silent no-op. |
| **2 — Naive** | Real but crude heuristics; works only on the easy/happy path. |
| **3 — Functional-limited** | Works for common cases; known gaps degrade real-world inputs. |
| **4 — Strong** | Robust across most real inputs; minor polish remaining. |
| **5 — Flawless** | Meets the vision; the output would be indistinguishable from the [Sunday Suspense benchmark](../product/quality-benchmark.md) on its matching dimension, produced with minimal effort. |

"Gap" = Target − Current. Priority reflects impact on deliverable quality × user trust, not effort.

---

## 2. Scorecard

### 2.1 Capabilities

| Capability | Current | Target | Gap | Headline reason for the gap |
|---|:---:|:---:|:---:|---|
| Character detection & Bible | 2 | 5 | **3** | Recall depends on LLM; exact-string aliasing; same-name merge bug; no casting traits; evidence hidden; no feedback loop |
| Manuscript understanding & structure | 2 | 5 | **3** | Discards DOCX/EPUB/TOC structure; English "Chapter N" only; destroys verse/scripts; multi-paragraph dialogue mishandled |
| Speaker attribution & dialogue | 3 | 5 | **2** | Deterministic two-speaker exchanges and scene-window LLM context exist; group-scene ambiguity and flat transcript review remain |
| Voice casting | 3 | 5 | **2** | Trait-ranked suggestions now use Kokoro facets and own-line auditions; no lineup/confusable-voice check yet |
| Performance direction | 2 | 5 | **3** | Direction transmission is truthful and managed Kokoro stays resident; inference is still crude and not evidence-based |
| Audio production quality | 1 | 5 | **4** | 16 kHz mono, aliasing resample, no loudness/limiter, no M4B, no metadata embedding |
| QA (catching real issues) | 1 | 5 | **4** | Checklist not listener; telemetry faked; rulebook checks unimplemented; no ASR verification |
| Review/patch workflow | 2 | 5 | **3** | Resolve-trap; patch can be a no-op; patch uses wrong voice; issue scoping bugs |

### 2.2 Cross-cutting principles (the multipliers)

These gate *every* capability; closing them is worth more than any single feature.

| Principle | Current | Target | Gap | Where it's broken today |
|---|:---:|:---:|:---:|---|
| **P1 — Live trust** ("ready/resolved/fixed" mean what they say) | 1 | 5 | **4** | Resolve-trap hides still-failing checks; patch no-op; render selection by random UUID |
| **P2 — Feedback loop** (corrections compound) | 0 | 5 | **5** | Corrections fix one row and are forgotten; no propagation, no few-shot reuse |
| **P3 — Evidence → one-click queues** | 1 | 5 | **4** | Rich evidence computed, hidden in JSON; reviews are inert text logs |
| **P4 — Honesty about engine capability** | 1 | 5 | **4** | No-op direction sliders; faked waveform/peak telemetry; "0 flags" = "approved" |
| **P5 — Use signal already present; LLM for judgment** | 1 | 5 | **4** | Format structure metadata, voice-ID facets, `segment_type`, `pauseAfterMs` all discarded |
| **P6 — Unified next-best-action** | 2 | 5 | **3** | Two parallel models (step rail + checklist), neither ranked by impact |

### 2.3 Foundational correctness (enablers, from the engineering report)

The vision assumes these hold. Today they don't, which is *why* P1 is a 1.

| Item | State | Consequence if unfixed |
|---|---|---|
| Render "latest" selection by random `uuid4` id (no `created_at`) | **Broken** | A patched segment can be silently excluded from the export — undermines the entire patch value prop |
| SQLite concurrency (no WAL/`busy_timeout`, unbounded thread-per-job, no render uniqueness) | **Broken** | `database is locked` errors and forked render history under normal use |
| No CI / no schema-drift guard | **Absent** | Regressions, doc drift, and the "compute-then-discard" defects persist unnoticed |

---

## 3. Per-capability gap detail

Format: **Current state → Vision target → Specific gaps (→ principle it serves)**.

### 3.1 Character detection & the Character Bible — 3 → 5
- **Current:** deterministic candidates only from segments already carrying a speaker hint; optional LLM enrichment gated on Ollama; title/nickname aliases, conservative spelling variants, and conflicting same-name evidence now route through review instead of unsafe automatic merges; gender/age/accent/role traits are extracted only from directly observed evidence; evidence is computed but not fully shown in the UI.
- **Target:** complete cast incl. narration-only characters; correct alias clusters with provenance; casting-relevant traits on every record; evidence attached; co-presence map; a tiny triage queue of genuine "same person?" decisions.
- **Gaps:**
  1. Narration-only characters invisible without LLM (→ P5).
  2. Full corpus-level alias clustering is still shallow beyond the bundled nickname and spelling-variant heuristics (→ P5).
  3. Richer co-presence and scene-distance disambiguation is still future work beyond the same-name trait gate (→ P1).
  4. Vocal-descriptor extraction remains limited beyond observed role, age, accent, and gender traits (→ P5).
  5. Evidence hidden in JSON; parser review is an inert log, not a queue (→ P3).
  6. No confirmation propagation or few-shot reuse of merges (→ P2).
  7. Merge-verification LLM prompt unbatched → collapses on large casts.

### 3.2 Manuscript understanding & structure — 2 → 5
- **Current:** container structure discarded (DOCX heading styles, EPUB spine + TOC); chapter detection requires literal English keywords; blanket line-wrap merge destroys verse/scripts pre-review; multi-paragraph dialogue demoted to narration; em-dashes destroyed; ASCII-only names; footnotes bleed into narration; English-only sentence/OCR.
- **Target:** format-and-typography-aware structure corroborated by TOC; front/back-matter classified; multi-paragraph/em-dash/script dialogue first-class; verse/plays preserve lines; language-adaptive; footnotes routed out; prosody-tuned segment boundaries.
- **Gaps:**
  1. Discards format metadata that gives the answer for free (→ P5) — **highest-leverage single gap here.**
  2. Chapter detection misses numeric/roman/centered headings.
  3. Destructive, irreversible clean pass on line-sensitive formats.
  4. Multi-paragraph dialogue misclassification.
  5. No front/back-matter classification.
  6. No language detection; English-only heuristics.
  7. Re-parse silently orphans downstream locks/edits on any offset shift (→ P1).
  8. Story-map review lacks previews, visual boundary markers, user-directed split (→ P3/P6).

### 3.3 Speaker attribution & dialogue — 3 → 5
- **Current:** deterministic attribution now has conservative nearby-turn, two-speaker alternation, speech-action, gendered pronoun-coreference, full same-scene active-speaker roster, interruption-exchange, and vocative-exchange hints for unlabeled dialogue; high-confidence missing speaker labels can be proposed back through Cast Discovery. The local LLM fallback receives bounded same-scene windows with an explicit active-speaker roster and target-only attribution writes. Transcript-level review and ambiguous group-scene attribution remain incomplete.
- **Target:** every line correctly attributed; back-and-forth resolves from turn-taking; scene speaker sets; differentiated confidence; rare, self-evident ambiguity; one fix resolves the pattern.
- **Gaps:**
  1. Coreference is limited to directly observed gender traits and nearby cues (→ P5).
  2. Scenes with more than two active speakers stay intentionally unresolved for human review (→ P5).
  3. Review is a flat grid, not a scene-level color-coded transcript (→ P3).

### 3.4 Voice casting — 3 → 5
- **Current:** existing project voices can expose derived Kokoro locale/gender facets, suggestions rank by character traits, and the Voice Bible can audition suggestions against an approved representative character line.
- **Target:** trait-matched, audibly distinct casting; auditioned against the character's own lines; a lineup comparison enforcing narrator/character contrast.
- **Gaps:** no full acoustic/personality facet model beyond provider IDs and observed traits; no cast-lineup comparison; no confusable-voice check enforcing narrator/character contrast (→ P3/P4).

### 3.5 Performance direction — 2 → 5
- **Current:** direction transmission is truthful for current engines and assembly honors per-segment pauses; managed Kokoro ONNX now has a resident local worker so its model stays loaded across previews/renders. Direction inference is still whole-segment substring matching, blind to speaker/scene/continuity/`segment_type`; XTTS still has no style/pace hook; Piper and XTTS remain subprocess-based.
- **Target:** context-aware, evidence-based, character-consistent direction that actually renders; natural micro-pacing; honest UI about engine limits.
- **Gaps:**
  1. Inference is crude and character-blind (→ P5).
  2. Evidence-based LLM direction remains unimplemented (→ P5).
  3. Persistent residency currently covers managed Kokoro only; Piper and XTTS still pay subprocess startup costs (→ P5).
  4. UI needs richer inline feedback for engine-specific direction ceilings beyond the current capability matrix (→ P4).

### 3.6 Audio production quality — 1 → 5
- **Current:** 16 kHz mono, linear-interpolation downsample (aliasing), hard-clip mix, fixed pauses, no room tone, no loudness/true-peak, ambience without crossfade/real ducking; MP3 without ID3/cover; M4B blocked; no retail sample; no real player/meters.
- **Target:** 44.1 kHz masters; LUFS-normalized + true-peak-limited; M4B with chapters/metadata/cover; tagged MP3; retail sample; QA scorecard; real waveform player.
- **Gaps:** every item above (→ mostly engineering + P4 for faked telemetry). Highest-leverage: loudness normalization + limiter, and 44.1 kHz resampling.

### 3.7 QA — 1 → 5
- **Current:** metadata/state checklist; the only audio-byte checks are duration, a naive clip threshold, and 100%-zero silence (dead against real speech); telemetry hardcoded; rulebook's loudness/pronunciation/truncation/voice-confusion checks unimplemented; nothing verifies the TTS said the words.
- **Target:** catches mispronunciation, wrong actor, flat delivery, truncation, loudness jumps, dead air, bad pacing.
- **Gaps:** real peak/RMS/LUFS/true-peak; RMS dead-air; duration-vs-text truncation; pronunciation-risk pre-flagging; **local ASR word-match** (the definitive intelligibility gate); render-time voice-consistency; flatness heuristic (→ P1/P4).

### 3.8 Review/patch workflow — 2 → 5
- **Current:** resolve-trap (resolved check stays hidden while still failing); patch never forces re-render (can be a silent no-op); patch re-renders in narrator voice/default direction (can *introduce* defects); chapter-issue and export-blocker scoping bugs; single global busy/error slot.
- **Target:** single-click causal fix using the right voice/direction, auto re-verified with before/after; ranked worklist; jump-to-timestamp verification.
- **Gaps:** fix the resolve-trap and patch no-op (→ P1); patch uses real voice/direction; auto-resolve on passing re-render (→ P1/P2); jump-to-audio waveform (→ P3); scope issues/export to selection; severity-ranked worklist (→ P6).

---

## 4. Prioritized gap register

Ranked by impact on flawless deliverables × trust (not effort). This is the raw input the roadmap sequences.

| # | Gap | Capability / Principle | Impact | Effort |
|---|---|---|:---:|:---:|
| G1 | Render "latest" ordering by random UUID → patches may not reach export | Foundational / P1 | Critical | M |
| G2 | Patch is a silent no-op (no forced re-render) + uses wrong voice/direction | Review / P1 | Critical | S |
| G3 | Resolve-trap: "ready" can be permanently wrong | QA / P1 | Critical | M |
| G4 | Direction not transmitted to engines (sliders no-op) | Direction / P4 | Critical | S–M |
| G5 | Audio quality ceiling: 44.1 kHz + loudness normalization + true-peak limiter | Audio | Critical | M |
| G6 | Feedback loop absent — corrections don't propagate or teach | All / P2 | High | M |
| G7 | Evidence hidden; reviews are logs not one-click queues | Char/Speaker/QA / P3 | High | M |
| G8 | Discarded format structure metadata (DOCX/EPUB/TOC) | Structure / P5 | High | S–M |
| G9 | Same-name character auto-merge (precision bug) + no fuzzy aliasing | Character / P1,P5 | High | M |
| G10 | No turn-taking / coreference for dialogue | Speaker | High | M |
| G11 | Real audio QA metrics (LUFS/clip/dead-air/truncation) | QA | High | M |
| G12 | SQLite concurrency + CI/schema-drift guard | Foundational | High | S–M |
| G13 | M4B + MP3 metadata/cover + retail sample | Audio | High | L |
| G14 | Casting traits + audition-first suggestions | Casting / P5 | Medium | M |
| G15 | Scene-level dialogue transcript review view | Speaker / P3 | Medium | M |
| G16 | Local ASR word-match verification | QA | Medium | L |
| G17 | Issue/export scoping to selection; severity-ranked worklist | Review / P6 | Medium | S |
| G18 | Multilingual structure, front/back-matter, footnotes, prosody segmentation | Structure | Medium | M–L |
| G19 | Persistent TTS worker (enables fast audition + evidence-LLM direction) | Direction/Audio | Medium | M |
| G20 | Unified next-best-action across the shell | All / P6 | Medium | M |

---

## 5. Reading of the gap

The largest gaps are **not** in the capability algorithms — they cluster in the **cross-cutting principles**, especially **P1 (live trust, gap 4)** and **P2 (feedback loop, gap 5)**. That is the central finding: Echodraft's individual stages sit at maturity 1–2, but they're each *pulled down* by shared foundational holes — faked trust signals, discarded intelligence, no compounding of human effort. Fixing a capability's algorithm while those holes remain yields little felt improvement, because the output still isn't trustworthy and the user's corrections still evaporate.

Conversely, the foundational/principle fixes (G1–G8, G12) are disproportionately **small effort for critical impact** — they're mostly wiring, honesty, and loop-closing on existing infrastructure. This asymmetry is what the roadmap exploits: close the multipliers first, then the per-capability algorithm work lands on a foundation where its gains are actually delivered and retained.
