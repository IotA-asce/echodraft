# Echodraft — Product Vision & Deep Capability Analysis

**Date:** 2026-07-03
**Updated:** 2026-07-05
**Question this answers:** Not "is the code clean?" but *"what would make Echodraft produce flawless audiobooks with an effortless workflow?"* — analyzed per production capability across both **algorithm quality** (does the output get better?) and **workflow/UX** (does the user reach a great result with the least effort and the most trust?).
**Method:** Six capability-focused analyses (character detection, manuscript structure, speaker attribution, casting & performance, audio production, QA & the review loop), each anchored to a "flawless target" and grounded in the current implementation. Findings that recurred across independent analyses are elevated to the cross-cutting principles in §2.

> **Completion update:** the Phase 0-4 roadmap that came from this analysis is now implemented. The sections below now describe the completed local-first baseline and separate any remaining ideas as post-roadmap polish.

---

## 1. The product vision

Echodraft's premise is right: an audiobook is not a one-shot TTS job, it's an **editable production** where a human directs and corrects at segment granularity. The completed Phase 0-4 roadmap now makes that premise operational: the pipeline computes evidence, delivers it into review, preserves human decisions, renders local audio truthfully, and rechecks the current artifact before approval/export.

A flawless Echodraft would feel like this to a creator:

> Import a manuscript in any format → it comes back correctly structured into chapters/scenes with the messy parts flagged, not silently mangled → the full cast is already discovered, de-duplicated, and aliased, with each character carrying casting-relevant traits → dialogue is attributed to the right speaker, and the handful of genuine ambiguities are triaged in a scene-view in minutes, not hundreds of context-free cards → voices are auto-suggested from character traits and auditioned against the character's *own* lines → performance direction is inferred with evidence and actually *heard* in the render → the produced chapter is mastered to publishable loudness and exported as a tagged, chapter-marked M4B → and at every step, a single "do this next" signal tells them the highest-impact thing to fix, with one click to hear exactly the moment in question.

The original analysis identified where that story broke. The current implementation has closed those roadmap breaks; remaining opportunities are refinements on top of the local-first production loop, not missing foundations.

**Concrete north star.** "Flawless" is otherwise unmeasurable, so this analysis anchors it to a real production that already exists: **Sunday Suspense**, the Bengali multi-voice audio-drama program from Radio Mirchi — a human-made instance of exactly what Echodraft generates (distinct voiced cast, narrator/dialogue separation, tasteful score and ambience under legible speech). The [Sunday Suspense quality benchmark](../../product/quality-benchmark.md) decomposes it into eight scored dimensions and, crucially, marks which are reachable with today's local models (most) and which sit at the local-TTS performance ceiling (expressive per-character *acting* — a tiering decision, not a bug). Read "flawless" throughout this document as "Sunday-Suspense-grade on the matching dimension."

---

## 2. Cross-cutting principles (the heart of "flawless")

Six independent analyses kept surfacing the same six ideas. These are the levers that, applied across every capability, turn "works" into "works flawlessly." **They matter more than any single feature.**

### P1 — "Ready / resolved / fixed" must be *live facts*, not stale opinions
**Completed baseline:** readiness now re-derives checks from current state, stale accepted risks re-surface when evidence changes, patch renders force fresh audio with the resolved voice/direction, latest render/export selection is deterministic, and listened approval is tied to the active chapter render.

**Principle:** every status is re-derived from the current artifact; resolution is system-verified on re-render; "accept risk / ignore" is a distinct human state that remains visible.

### P2 — Close the human-in-the-loop feedback loop
**Completed baseline:** confirmed speaker rows, cast merges, rejected duplicate decisions, and locks now persist as project facts and are reused by later parser, cast, attribution, and review passes. This makes the review burden shrink over time instead of resetting on every rerun.

### P3 — Surface the evidence you already compute; turn logs into one-click queues
**Completed baseline:** parser warnings, cast duplicate/confirmation actions, speaker attribution evidence, direction evidence, readiness findings, waveform issue markers, and export blockers now feed actionable review surfaces instead of inert logs.

**Principle:** every ambiguity is an actionable card or timeline marker with its evidence attached and an obvious next action.

### P4 — Be honest in the UI about what the engine can actually do
**Completed baseline:** supported direction controls are transmitted to engines, capability metadata is explicit, real waveform/audio measurements feed QA, and "no automated issues" is separate from "listened and approved."

**Principle:** show real per-engine capability at the point of control, show real measurements, and keep automated checks distinct from human approval.

### P5 — Use the signal that's already in the input; reserve the LLM for judgment
**Completed baseline:** DOCX/EPUB/TOC structure, front/back matter headings, language signals, segment type, pauses, Kokoro voice-ID facets, active-speaker rosters, deterministic direction hints, and confirmed cast/speaker facts are used before optional local LLM judgment.

**Principle:** deterministic passes carry recall/precision; the local LLM is used with bounded context for the cases that need semantic judgment.

### P6 — One unified "next best action," everywhere
**Completed baseline:** the workflow shell now merges step progress, readiness findings, export blockers, transcript markers, and approval state into one ranked next-best-action card with deep links to the relevant control, segment, or audio moment.

---

## 3. Capability deep-dives

Each section: completed baseline → the flawless target → post-roadmap polish opportunities.

### 3.1 Character detection & the Character Bible

**Completed baseline.** Cast discovery creates deterministic and optional local LLM candidates, preserves canonical names/aliases/traits, gates unsafe same-name merges, routes fuzzy duplicate and low-confidence candidates into review, and reuses confirmed speaker/cast facts in later passes. Character traits feed voice suggestions and own-line auditions.

**Flawless target.** Complete cast including quiet/narration-only characters; correct alias clusters with a canonical name and visible provenance; gender/age/role/vocal-descriptor on every record as casting input; evidence attached to every claim; a lightweight co-presence map (who shares scenes with whom) for disambiguation and voice-contrast; a review queue that's a small set of genuine "is this the same person?" decisions.

**Post-roadmap polish.** Full corpus-level alias graphs, richer co-presence disambiguation, broader narration-only recall, and deeper vocal descriptors can continue improving cast quality.

### 3.2 Manuscript understanding & structure

**Completed baseline.** The parser preserves container chapter signals from DOCX headings and EPUB spine/TOC, classifies explicit front/back matter, keeps multi-paragraph dialogue as dialogue, routes footnote-like paragraphs to review, detects language at document and chapter level, and uses clause-aware prosody fallback for overlong narration.

**Flawless target.** Format-and-typography-aware structure (numeric/roman/all-caps/centered headings), corroborated by TOC; front/back-matter classified as distinct non-narrative zones (dedication, epigraph, TOC, afterword, index, about-the-author) and excluded from cast discovery; multi-paragraph, em-dash, and colon-script dialogue all first-class; poetry/plays preserve line structure; language detected and segmentation/OCR/name-matching adapt; footnotes routed out of the narration stream; segments cut at prosodic boundaries, never mid-clause.

**Post-roadmap polish.** Numeric/roman/centered heading breadth, typography-only matter, language-adaptive OCR/name/TTS behavior, more em-dash/script dialogue forms, and line-sensitive verse/play preservation can deepen structure handling.

### 3.3 Speaker attribution & dialogue

**Completed baseline.** Attribution has conservative deterministic help for nearby turns, same-scene two-speaker alternation, speech-action cues, gendered pronoun coreference, full same-scene active-speaker rosters, interruption exchanges, vocative exchanges, and confident cast-back proposals. The LLM pass sees bounded same-scene windows with an explicit active-speaker roster and only writes back target unresolved segment IDs. Scene-level transcript review color-codes speakers and links waveform issue markers to the active audio moment.

**Flawless target.** Every line attributed to one speaker (named or explicit narrator/unknown, never a silent narrator default); rapid back-and-forth resolves from turn-taking; group scenes track a live speaker roster; interruptions/trailing-off stay attributed; confidence differentiated by rule type; uncertainty rare and self-evidently worth a human's time; **one human fix resolves the pattern.**

**Post-roadmap polish.** Broader group-scene coreference, more keyboard-driven transcript triage, and bulk operations can further reduce review time.

### 3.4 Voice casting & performance direction

**Completed baseline.** Casting has a trait-ranked suggestion path: `VoiceProfile` exposes derived Kokoro locale/gender facets, suggestions compare those facets with observed character traits, and the Voice Bible can audition a suggested voice against the character's own approved dialogue. Managed Kokoro ONNX keeps a resident local worker alive across previews/renders, so its model no longer reloads for every line. Opt-in local LLM direction inference uses same-scene `TARGET`/`CONTEXT` windows with segment type, speaker candidate/approved attribution, mood continuity, deterministic hints, and persisted evidence.

**Flawless target.** Distinct, trait-matched casting audibly separable from narrator and from other in-scene characters; per-character consistency across the whole book; context-aware emotion/pace/pause that *actually renders*; natural micro-pacing from punctuation + directed intent; genre-appropriate narrator tone; and complete honesty about the local-engine ceiling.

**Post-roadmap polish.** Cast-lineup comparison, confusable-voice checks, deeper acoustic/personality facets, richer direction evidence review, and more scene mood tooling can improve production control.

### 3.5 Audio production quality

**Completed baseline.** Chapter assembly uses a 44.1 kHz mastered path with band-limited resampling, loudness normalization, true-peak limiting, calibrated room tone, direction-aware pauses, real QA metrics, MP3 ID3/cover metadata, M4B chapters/metadata/artwork, retail sample support, and waveform-backed review.

**Flawless target.** 44.1 kHz/16-bit masters; MP3 ≥192 kbps with embedded ID3 + cover; **M4B with chapter markers, metadata, and artwork** as the flagship; integrated loudness in the ACX window (−23…−18 LUFS) consistent ±0.5–1 LU chapter-to-chapter; true-peak ≤ −3 dBTP via a lookahead limiter; verified noise floor; direction-aware pacing + room tone; crossfaded ambience with real sidechain ducking; auto retail sample; and a QA scorecard on every export.

**Post-roadmap polish.** More mastering previews, meters, and advanced ambience ducking/crossfade controls can make the audio workspace richer.

### 3.6 QA & the review/patch workflow

**Completed baseline.** QA uses real audio telemetry, readiness re-derives live state, optional local ASR verifies spoken words against expected text, patches force fresh audio using resolved voice/direction, passing rerenders auto-resolve relevant findings, transcript/waveform review jumps to issue moments, chapter/export blockers are scoped, and chapter approval is separate from automated checks.

**Flawless target.** "Ready" is a live fact; QA catches what actually ruins audiobooks (mispronunciation, wrong actor, monotone where text implies emotion, truncated TTS, loudness jumps, dead air, bad pacing); fixing a line is single-click, uses the right voice/direction, and auto-re-verifies with a before/after; every screen shows one ranked "do this next"; verification is jump-to-timestamp, never a full re-listen.

**Post-roadmap polish.** Timestamped/chapter-level ASR alignment, pronunciation-risk preflagging, render-time voice consistency, and flatness heuristics remain useful future QA layers.

---

## 4. Unified roadmap completion

The six analyses independently converged on the same sequencing wisdom: **repair the loops and the honesty first, then upgrade the algorithms, then add the delighters.** The completed roadmap followed that order:

### Phase 0 — Trust foundation
Render/export ordering, patch rerender correctness, live readiness, SQLite/worker hardening, and CI/schema drift guard were completed.

### Phase 1 — Honesty and compounding loop
Direction transmission, correction propagation, evidence triage, and container-derived structure signals were completed.

### Phase 2 — Publishable audio
Mastered audio, real audio QA, and export polish including M4B/MP3 metadata/retail samples were completed.

### Phase 3 — Algorithmic depth
Character disambiguation, speaker attribution depth, casting traits/auditions, persistent local TTS worker, ASR verification, evidence-based direction inference, and structure depth were completed.

### Phase 4 — Workflow experience
Scene-level transcript review, scoped issues/export blockers, ranked readiness worklists, unified next-best action, and listened chapter approval were completed.

---

## 5. The through-line

The recurring lesson across all six capabilities was that **Echodraft already thought harder than it acted**. The completed roadmap closes that loop: evidence is surfaced, controls are honest, current-state checks are live, human corrections compound, and the next action is ranked. The product now has the intended local-first audiobook production loop; future work should refine breadth and polish rather than repair foundational trust.

---

*Companion document: [`deep-analysis-report.md`](deep-analysis-report.md) covers the code-correctness and engineering findings (render-ordering bug, concurrency, CI). This document is the product/algorithm/workflow lens; where they overlap (render ordering, direction transmission, stubbed QA), the two reach the same conclusions from different angles.*
