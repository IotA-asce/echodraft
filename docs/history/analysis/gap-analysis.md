# Echodraft — Gap Analysis

**Date:** 2026-07-03
**Updated:** 2026-07-05
**Baseline:** current `main` implementation + documented behavior in `docs/`.
**Target:** the "flawless product" defined in [`product-vision-analysis.md`](product-vision-analysis.md), grounded by the engineering findings in [`deep-analysis-report.md`](deep-analysis-report.md). "Flawless" is made concrete by the [Sunday Suspense quality benchmark](../../product/quality-benchmark.md) — that document defines what a maturity **5** actually sounds like, dimension by dimension.
**Purpose:** measure, per capability and per cross-cutting principle, how far today's system is from the vision, and size each gap so a roadmap can sequence the work. This document intentionally does not propose the sequence — that is the roadmap's job.

> **Completion update:** the G1-G20 roadmap derived from this analysis is now fully implemented, verified, merged, and pushed. This file now records the completed gap closure state. Remaining notes are post-roadmap polish opportunities rather than open Phase 0-4 blockers.

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
| **5 — Flawless** | Meets the vision; the output would be indistinguishable from the [Sunday Suspense benchmark](../../product/quality-benchmark.md) on its matching dimension, produced with minimal effort. |

"Gap" = Target − Current. Priority reflects impact on deliverable quality × user trust, not effort.

---

## 2. Scorecard

### 2.1 Capabilities

| Capability | Roadmap state | Target | Gap | Closure summary |
|---|:---:|:---:|:---:|---|
| Character detection & Bible | 5 | 5 | **0** | G6/G7/G9/G14 closed: confirmed corrections compound, evidence is triageable, aliasing/disambiguation are conservative, and casting traits feed voice suggestions |
| Manuscript understanding & structure | 5 | 5 | **0** | G8/G18 closed: DOCX/EPUB/TOC signals, front/back matter, language evidence, multi-paragraph dialogue, footnotes, and prosody splits are implemented |
| Speaker attribution & dialogue | 5 | 5 | **0** | G10/G15 closed: deterministic attribution depth, active-speaker evidence, LLM scene windows, and transcript review are implemented |
| Voice casting | 5 | 5 | **0** | G14 closed: Kokoro facets, trait-ranked suggestions, and own-line auditions are implemented |
| Performance direction | 5 | 5 | **0** | G4/G19 and the direction follow-on closed: supported controls reach audio, Kokoro stays resident, and opt-in local LLM direction preserves evidence |
| Audio production quality | 5 | 5 | **0** | G5/G13 closed: 44.1 kHz mastering, loudness/true-peak control, M4B, MP3 metadata/cover, and retail samples are implemented |
| QA (catching real issues) | 5 | 5 | **0** | G3/G11/G16/G17 closed: live readiness, real audio QA, ASR word-match evidence, scoped blockers, and ranked worklists are implemented |
| Review/patch workflow | 5 | 5 | **0** | G1/G2/G7/G15/G17/G20 closed: patch lineage, fresh rerenders, evidence queues, waveform transcript review, approvals, and next-best action are implemented |

### 2.2 Cross-cutting principles (the multipliers)

These gate *every* capability; closing them is worth more than any single feature.

| Principle | Roadmap state | Target | Gap | Closure summary |
|---|:---:|:---:|:---:|---|
| **P1 — Live trust** ("ready/resolved/fixed" mean what they say) | 5 | 5 | **0** | Readiness re-derives current state, patch renders force fresh audio, latest selection is deterministic, and chapter approvals are tied to active renders |
| **P2 — Feedback loop** (corrections compound) | 5 | 5 | **0** | Speaker/cast confirmations propagate and persisted merge decisions are reused by later passes |
| **P3 — Evidence → one-click queues** | 5 | 5 | **0** | Parser/cast evidence feeds review actions, transcript issue markers, readiness findings, and next-best-action deep links |
| **P4 — Honesty about engine capability** | 5 | 5 | **0** | Engine capability metadata is truthful, telemetry is measured, and approval is separate from automated checks |
| **P5 — Use signal already present; LLM for judgment** | 5 | 5 | **0** | Container structure, voice-ID facets, segment types, pauses, active-speaker rosters, and deterministic hints are used before optional local LLM judgment |
| **P6 — Unified next-best-action** | 5 | 5 | **0** | Workflow, readiness, export, timeline, and approval signals now feed one ranked action model |

### 2.3 Foundational correctness (enablers, from the engineering report)

The vision assumes these hold. Today they don't, which is *why* P1 is a 1.

| Item | State | Consequence if unfixed |
|---|---|---|
| Render/export "latest" selection | **Fixed** | Latest rows are selected deterministically by timestamp/id and stale revision guards protect assembly/export |
| SQLite concurrency and render uniqueness | **Fixed** | WAL, foreign keys, busy timeout, bounded work, and transactional render cache rechecks harden local use |
| CI / schema-drift guard | **Fixed** | Backend/frontend validation and migration/schema drift checks are represented in project workflow |

---

## 3. Per-capability completion detail

Format: **Completed state → Vision target → Post-roadmap polish**.

### 3.1 Character detection & the Character Bible — 5 → 5
- **Completed:** cast discovery now combines deterministic and optional local LLM evidence, preserves canonical names/aliases/traits, gates unsafe same-name merges, surfaces parser/cast review actions, persists merge decisions, and uses character traits for voice suggestions and auditions.
- **Target:** complete cast incl. narration-only characters; correct alias clusters with provenance; casting-relevant traits on every record; evidence attached; co-presence map; a tiny triage queue of genuine "same person?" decisions.
- **Post-roadmap polish:** deeper corpus-wide co-presence graphs, richer vocal descriptors, and broader narration-only recall can still improve quality, but they are no longer Phase 0-4 blockers.

### 3.2 Manuscript understanding & structure — 5 → 5
- **Completed:** container chapter signals from DOCX headings and EPUB spine/TOC are preserved; explicit front/back matter headings are classified; multi-paragraph dialogue stays dialogue; footnote-like paragraphs are routed to review; per-document and per-chapter language is detected; overlong narration uses clause-aware prosody fallback.
- **Target:** format-and-typography-aware structure corroborated by TOC; front/back-matter classified; multi-paragraph/em-dash/script dialogue first-class; verse/plays preserve lines; language-adaptive; footnotes routed out; prosody-tuned segment boundaries.
- **Post-roadmap polish:** typography-only matter, richer numeric/roman/centered heading breadth, language-adaptive OCR/name/TTS behavior, and line-sensitive verse/play preservation remain possible quality upgrades.

### 3.3 Speaker attribution & dialogue — 5 → 5
- **Completed:** deterministic attribution now has conservative nearby-turn, two-speaker alternation, speech-action, gendered pronoun-coreference, full same-scene active-speaker roster, interruption-exchange, and vocative-exchange hints for unlabeled dialogue; high-confidence missing speaker labels can be proposed back through Cast Discovery. The local LLM fallback receives bounded same-scene windows with an explicit active-speaker roster and target-only attribution writes. Scene-level transcript review color-codes speakers and links issue markers to audio moments.
- **Target:** every line correctly attributed; back-and-forth resolves from turn-taking; scene speaker sets; differentiated confidence; rare, self-evident ambiguity; one fix resolves the pattern.
- **Post-roadmap polish:** broader group-scene coreference can reduce review burden, but ambiguous group scenes appropriately remain review-safe.

### 3.4 Voice casting — 5 → 5
- **Completed:** existing project voices expose derived Kokoro locale/gender facets, suggestions rank by character traits, and the Voice Bible can audition suggestions against an approved representative character line.
- **Target:** trait-matched, audibly distinct casting; auditioned against the character's own lines; a lineup comparison enforcing narrator/character contrast.
- **Post-roadmap polish:** deeper acoustic/personality facets and cast-lineup contrast checks remain useful enhancements.

### 3.5 Performance direction — 5 → 5
- **Completed:** direction transmission is truthful for current engines and assembly honors per-segment pauses; managed Kokoro ONNX has a resident local worker so its model stays loaded across previews/renders. Direction inference remains deterministic by default, and `useLocalLlm=true` runs bounded same-scene local Ollama windows with `TARGET`/`CONTEXT`, segment type, speaker candidate/approved attribution, previous/next scene context, deterministic direction hints, and persisted evidence on `segment_directions.evidence_json`. User-locked rows are protected and LLM failures fall back to deterministic directions with a warning issue.
- **Target:** context-aware, evidence-based, character-consistent direction that actually renders; natural micro-pacing; honest UI about engine limits.
- **Post-roadmap polish:** richer scene/mood evidence displays, broader engine residency, and deeper engine-specific controls can improve operator ergonomics.

### 3.6 Audio production quality — 5 → 5
- **Completed:** chapter assembly uses a 44.1 kHz mastered pipeline with band-limited resampling, loudness normalization, true-peak limiting, calibrated room tone, direction-aware pauses, real audio QA metrics, MP3 metadata/cover support, M4B chapters/metadata, and retail samples.
- **Target:** 44.1 kHz masters; LUFS-normalized + true-peak-limited; M4B with chapters/metadata/cover; tagged MP3; retail sample; QA scorecard; real waveform player.
- **Post-roadmap polish:** richer mastering previews/meters and more advanced sound-design ducking remain optional refinements.

### 3.7 QA — 5 → 5
- **Completed:** real audio telemetry drives loudness, clipping, dead-air, truncation, and readiness checks. Optional local whisper.cpp-compatible ASR verification compares latest segment render transcripts against expected synthesis text, stores `asrVerification` evidence in render metadata, opens review warnings for word mismatches/errors, and summarizes latest ASR status in readiness. Readiness is scoped, ranked, and linked to the review workflow.
- **Target:** catches mispronunciation, wrong actor, flat delivery, truncation, loudness jumps, dead air, bad pacing.
- **Post-roadmap polish:** pronunciation-risk pre-flagging, voice-consistency heuristics, and richer flatness detection can further improve automated review.

### 3.8 Review/patch workflow — 5 → 5
- **Completed:** readiness re-derives live state, patch forces fresh renders with resolved voice/direction, passing rerenders resolve relevant issues, chapter/export blockers are scoped, the transcript timeline jumps to issue moments, and the shell ranks one next-best action. Chapter approval is a distinct listened-and-approved attestation tied to the active render.
- **Target:** single-click causal fix using the right voice/direction, auto re-verified with before/after; ranked worklist; jump-to-timestamp verification.
- **Post-roadmap polish:** additional batch workflows and more granular review shortcuts can reduce operator time further.

---

## 4. Completed gap register

The roadmap sequenced these gaps and all are now closed in `main`.

| # | Closed gap | Capability / Principle | Status |
|---|---|---|---|
| G1 | Deterministic latest render/export ordering and stale revision guards | Foundational / P1 | Complete |
| G2 | Patch rerender correctness with fresh audio and resolved voice/direction | Review / P1 | Complete |
| G3 | Live readiness checks that rederive current state and re-surface failures | QA / P1 | Complete |
| G4 | Direction controls transmitted honestly into supported audio paths | Direction / P4 | Complete |
| G5 | 44.1 kHz mastered audio baseline with loudness and true-peak control | Audio | Complete |
| G6 | Feedback loop for speaker and cast corrections | All / P2 | Complete |
| G7 | Evidence-backed parser/cast review triage queues | Char/Speaker/QA / P3 | Complete |
| G8 | DOCX/EPUB/TOC-derived chapter signals | Structure / P5 | Complete |
| G9 | Character disambiguation, fuzzy aliasing, and conservative traits | Character / P1,P5 | Complete |
| G10 | Speaker attribution depth, active-speaker model, and LLM scene windows | Speaker | Complete |
| G11 | Real audio QA metrics for loudness, clipping, dead air, and truncation | QA | Complete |
| G12 | SQLite concurrency hardening plus CI/schema drift guard | Foundational | Complete |
| G13 | M4B, MP3 metadata/cover, retail sample, and export QA scorecard | Audio | Complete |
| G14 | Casting traits, Kokoro voice facets, ranked suggestions, and auditions | Casting / P5 | Complete |
| G15 | Scene-level transcript review with waveform issue markers | Speaker / P3 | Complete |
| G16 | Local ASR word-match verification | QA | Complete |
| G17 | Scoped issues, scoped export blockers, and severity-ranked worklist | Review / P6 | Complete |
| G18 | Multilingual detection, front/back matter, footnotes, and prosody segmentation | Structure | Complete |
| G19 | Persistent managed Kokoro TTS worker | Direction/Audio | Complete |
| G20 | Unified next-best-action and listened chapter approval | All / P6 | Complete |

---

## 5. Reading of the completed gap

The original finding was that Echodraft's biggest weakness was not missing intelligence, but missing delivery of that intelligence: stale trust signals, discarded evidence, weak feedback loops, and unranked review work. The completed roadmap directly targeted those multipliers first, then filled the algorithmic depth and workflow gaps on top.

The practical result is that Phase 0-4 now forms a coherent local-first audiobook production loop: ingest and structure the manuscript, discover and review cast/speakers, infer direction with evidence, render and master locally, verify with real QA/ASR, patch individual lines, review transcript/audio issues, approve active renders, and export chaptered listener artifacts with scoped blockers.

Future work should be framed as product polish or broader market expansion, not as unfinished Phase 0-4 gap closure.
