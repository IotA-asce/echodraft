# Echodraft — Product Vision & Deep Capability Analysis

**Date:** 2026-07-03
**Question this answers:** Not "is the code clean?" but *"what would make Echodraft produce flawless audiobooks with an effortless workflow?"* — analyzed per production capability across both **algorithm quality** (does the output get better?) and **workflow/UX** (does the user reach a great result with the least effort and the most trust?).
**Method:** Six capability-focused analyses (character detection, manuscript structure, speaker attribution, casting & performance, audio production, QA & the review loop), each anchored to a "flawless target" and grounded in the current implementation. Findings that recurred across independent analyses are elevated to the cross-cutting principles in §2.

---

## 1. The product vision

Echodraft's premise is right: an audiobook is not a one-shot TTS job, it's an **editable production** where a human directs and corrects at segment granularity. The architecture already honors that. What separates the current alpha from a *complete product* is not features — it's that the pipeline **computes far more intelligence than it delivers**, and the parts of the workflow that are supposed to build confidence (the "ready" light, the "fix this line" button, the direction sliders, the waveform panel) frequently don't mean what they appear to mean.

A flawless Echodraft would feel like this to a creator:

> Import a manuscript in any format → it comes back correctly structured into chapters/scenes with the messy parts flagged, not silently mangled → the full cast is already discovered, de-duplicated, and aliased, with each character carrying casting-relevant traits → dialogue is attributed to the right speaker, and the handful of genuine ambiguities are triaged in a scene-view in minutes, not hundreds of context-free cards → voices are auto-suggested from character traits and auditioned against the character's *own* lines → performance direction is inferred with evidence and actually *heard* in the render → the produced chapter is mastered to publishable loudness and exported as a tagged, chapter-marked M4B → and at every step, a single "do this next" signal tells them the highest-impact thing to fix, with one click to hear exactly the moment in question.

Every gap below is a place where that story currently breaks. The encouraging finding: the fixes are mostly **wiring, honesty, and closing loops** on top of infrastructure that already exists — not new subsystems.

**Concrete north star.** "Flawless" is otherwise unmeasurable, so this analysis anchors it to a real production that already exists: **Sunday Suspense**, the Bengali multi-voice audio-drama program from Radio Mirchi — a human-made instance of exactly what Echodraft generates (distinct voiced cast, narrator/dialogue separation, tasteful score and ambience under legible speech). The [Sunday Suspense quality benchmark](../product/quality-benchmark.md) decomposes it into eight scored dimensions and, crucially, marks which are reachable with today's local models (most) and which sit at the local-TTS performance ceiling (expressive per-character *acting* — a tiering decision, not a bug). Read "flawless" throughout this document as "Sunday-Suspense-grade on the matching dimension."

---

## 2. Cross-cutting principles (the heart of "flawless")

Six independent analyses kept surfacing the same six ideas. These are the levers that, applied across every capability, turn "works" into "works flawlessly." **They matter more than any single feature.**

### P1 — "Ready / resolved / fixed" must be *live facts*, not stale opinions
The product's trust signals are currently detached from reality:
- **Readiness** permanently hides a check once a human clicks "resolve," even if the underlying condition (e.g. "narrator voice missing") is *still failing* on every subsequent run — the score reads `ready` forever, and there's no "reopen." (QA analysis, `readiness.py:70-97, 587-591`.)
- **"Fix this line"** can be a complete no-op: patch never sets `force: true`, so for any issue that doesn't change text/voice/direction (clipping, silence, truncation, corrupt audio) the cached identical render is returned and QA never re-runs — the user sees "patched," nothing changed (`rendering.py:44-56`, `project-dashboard.tsx:221`).
- **Render selection** for assembly/export sorts by a *random UUID* (no `created_at`), so a genuinely-fixed segment may still be excluded from the exported chapter ~50% of the time (see companion code report; verified).

**Principle:** every status is re-derived from the current artifact; resolution is system-verified on re-render; "accept risk / ignore" is a distinct, time-boxed, human-only state that re-surfaces when content changes.

### P2 — Close the human-in-the-loop feedback loop
Today a user's correction is a dead end: it fixes one row and is forgotten. In a flawless product **every human decision has leverage**:
- Confirming a speaker propagates to identical/adjacent lines and re-scores the rest of the exchange via turn-taking.
- Confirming a character merge ("Liz = Elizabeth") resolves sibling review issues *and* becomes a persisted alias fact *and* a few-shot exemplar injected into future LLM passes for that project.
- Adding a pronunciation from a QA flag immediately re-queues affected segments.
- A corrected direction seeds the inference model.

This single principle is what makes the review burden *shrink over time* within a project instead of being re-derived from scratch on every rerun.

### P3 — Surface the evidence you already compute; turn logs into one-click queues
The backend computes rich evidence — mention counts, first-seen offsets, candidate graphs, confidence, `unsupportedDirection` — and then hides most of it in JSON blobs the UI never reads (`character.notes`, evidence graphs, per-adapter capability). Reviews are rendered as **inert text logs** the user must manually translate into actions in a *different* screen.

**Principle:** every ambiguity is an actionable card with its evidence attached (the quote, the count, the "why") and one-click resolutions (Accept / Merge into ranked suggestion / Reassign / Ignore). Triage becomes reading-comprehension-free.

### P4 — Be honest in the UI about what the engine can actually do
The product advertises capabilities it doesn't deliver, which is worse than not having them because it erodes trust silently:
- Direction pace/style are shown as sliders and echoed back as `effectiveDirection`, but **never reach Kokoro or XTTS** (managed Kokoro hardcodes `speed=1.0`; XTTS never receives the style prompt). Only Piper honors its controls.
- Waveform/peak/silence telemetry is **hardcoded placeholder data** (`peak:0`, `waveform:[]`, `silenceRanges:[[0,dur]]`) presented as real measurement.
- "Review complete" is set when zero automated flags exist — conflated with "a human listened and approved."

**Principle:** show real per-engine capability at the point of control (gray out / label "engine preview only"), show real measurements, and separate "no automated issues" from "human-approved."

### P5 — Use the signal that's already in the input; reserve the LLM for judgment
A local-first tool should extract maximum determinism from what it already has, so it works well with **no model installed**, and spend the LLM only on genuine ambiguity:
- Container formats hand you structure for free: DOCX `Heading 1/2` styles and EPUB spine boundaries + `nav.xhtml`/`toc.ncx` TOC — **all discarded today** in favor of reverse-engineering chapters from flattened text with English regex.
- Kokoro voice IDs encode locale+gender (`af_*`/`am_*`/`bf_*`/`bm_*`) — discarded instead of driving casting suggestions.
- `segment_type` (dialogue vs narration), `pauseAfterMs`, and the pronunciation dictionary are computed and then ignored at the point they'd matter.

**Principle:** deterministic passes (proper-noun NER, nickname lexicons, Jaro-Winkler, coreference, format metadata, turn-taking) carry recall/precision; the local LLM is used with real scene context + few-shot from confirmed examples for the cases that need semantic judgment.

### P6 — One unified "next best action," everywhere
There are two parallel mental models today (the guided step rail and the readiness checklist) and neither ranks by impact. A flawless product collapses them into a single worklist: blocking issues first, then highest listener-impact, with a "do this next" card and a deep link to the exact control or timestamp. The user is never asked to scan and prioritize a flat list themselves.

---

## 3. Capability deep-dives

Each section: where output/UX breaks today → the flawless target → the algorithm upgrade path → the workflow/UX redesign → the priority calls. Effort: **S** ≈ hours–1 day, **M** ≈ 1–3 days, **L** ≈ week+.

### 3.1 Character detection & the Character Bible

**Where it breaks.** Recall depends on the LLM being installed — deterministic candidates are only generated from segments that *already* have a speaker hint (`cast_discovery.py:190-227`), so a character described in narration but never tagged as speaking is invisible without Ollama. Alias linking is exact-string only; the sole fuzzy path (`_soft_name_match`) is a substring/honorific check that doesn't resolve Liz↔Elizabeth or Darcy↔Fitzwilliam. **A real precision bug:** `CharacterIndex.exact()` fuses two different same-first-name characters (two "John"s) into one record before any disambiguation (`cast_discovery.py:140-145, 364-367`). No casting-relevant attributes exist (no gender/age/accent — only a 4-value role enum). Rich evidence is computed (`_candidate_evidence_graph`) and never shown. Corrections don't propagate or feed forward.

**Flawless target.** Complete cast including quiet/narration-only characters; correct alias clusters with a canonical name and visible provenance; gender/age/role/vocal-descriptor on every record as casting input; evidence attached to every claim; a lightweight co-presence map (who shares scenes with whom) for disambiguation and voice-contrast; a review queue that's a small set of genuine "is this the same person?" decisions.

**Algorithm path.** *Deterministic (ship regardless of LLM):* full-narration proper-noun candidate generation; a bundled nickname/diminutive lexicon; Jaro-Winkler + title-stripped-surname matching (extend honorifics beyond `{dr,captain,capt,prof}`); alias clustering as a union-find graph over name-similarity + co-occurrence edges (handles transitive A↔B↔C aliasing the current exact-key consolidation can't); **a disambiguation gate before same-name auto-merge** (check scene distance + co-occurring names); lightweight recency+gender coreference for pronoun tags. *LLM-assisted:* extend the extraction schema with `genderGuess`/`ageBandGuess`/`vocalDescriptor`; map-reduce the merge-verification pass (it currently dumps *all* cast + *all* candidates into one prompt — collapses on large casts); carry a rolling "known cast" summary across discovery batches; inject user-confirmed merges as few-shot exemplars.

**Workflow/UX.** Turn "Parser Review" from an inert text log (`StructureWarnings.tsx`) into an accept/merge/reject queue using the already-computed evidence. Replace the alphabetical "Merge into…" dropdown with a *ranked* "Is this the same person?" card showing side-by-side evidence quotes. Expose the evidence graph on character cards. Bulk operations ("these 6 are narrator asides — dismiss all"). Propagate confirmations to sibling issues immediately. A "seen but unvoiced" tray so narration-only characters aren't dropped from casting.

**Priorities:** disambiguation gate before same-name merge **(algorithm, M)** · nickname lexicon + fuzzy alias linking **(algorithm, S/M)** · surface evidence on cards **(workflow, S)** · actionable triage queue **(workflow, M)** · gender/age/vocal fields for casting **(both, M)** · full-narration candidate generation **(algorithm, M)**.

### 3.2 Manuscript understanding & structure

**Where it breaks.** Ingestion **discards the structure the file already carries**: DOCX extraction joins paragraph text and drops `Heading 1/2` styles (`ingestion.py:239`); EPUB flattens spine items and ignores the TOC (`ingestion.py:242-256`). Chapter detection then requires the literal English word "Chapter/Part/…" — books numbered `1,2,3` or `I,II,III` produce **zero chapters** and collapse to one "Unresolved chapter." A blanket line-wrap merge (`cleaning.py:173-189`) flattens poetry/plays/lists into run-on prose *before* the user sees anything, with no undo. Duplicate-adjacent-paragraph removal can silently delete real repeated dialogue ("No." / "No."). Multi-paragraph dialogue is demoted to narration. Em-dashes are destroyed in normalization; names are ASCII-only; footnotes bleed into narration; sentence segmentation and OCR are English-only.

**Flawless target.** Format-and-typography-aware structure (numeric/roman/all-caps/centered headings), corroborated by TOC; front/back-matter classified as distinct non-narrative zones (dedication, epigraph, TOC, afterword, index, about-the-author) and excluded from cast discovery; multi-paragraph, em-dash, and colon-script dialogue all first-class; poetry/plays preserve line structure; language detected and segmentation/OCR/name-matching adapt; footnotes routed out of the narration stream; segments cut at prosodic boundaries, never mid-clause.

**Algorithm path.** Read container metadata as ground truth (biggest fix, low effort — the signal is in the file). Broaden heading detection + TOC cross-check as a validator that *warns on disagreement*. Front/back-matter classification pass with a `matter_type`. Scene-scoped quote scanner with an "open dialogue block" state for multi-paragraph speech. Document-level (and per-chapter) language detection feeding sentence rules, OCR `-l`, and TTS language. Scene breaks from three independent signal families (time / place / POV shift), not one keyword list. Prosody-tuned segment boundaries (prefer sentence/paragraph/dialogue-tag cuts; clause-level fallback). Positional footnote detection via the existing PDF page-render pipeline. LLM only for ambiguous heading/scene calls, on small windows, with the existing no-echo validation discipline.

**Workflow/UX.** Ask "what kind of book is this?" (detect verse/script) *before* the destructive clean pass, and keep raw text revertible per section. Clean Text Review as a real before/after diff with per-change revert (not just "mark reviewed," which today doesn't mutate anything). Story Map shows scene titles/previews (not "Scene 1/2/3") with draggable boundary markers over the text. **User-directed split** at a chosen cursor/selection offset instead of the automatic midpoint cut (which forces a split→merge→edit workaround today). A **pre-reparse impact preview** ("N of your M edits are in shifted regions and will be re-mapped; K need re-review") plus content-anchored locks, because any upstream edit currently silently orphans every downstream lock via exact-offset ID matching. A fast per-segment TTS scrub in Story Map before committing a full chapter render.

**Priorities:** read DOCX/EPUB/TOC structure **(algorithm, S/M — highest leverage)** · conditional/reversible line-wrap merge **(both, M)** · broaden heading detection + TOC cross-check **(algorithm, M)** · scene-scoped multi-paragraph dialogue **(algorithm, M)** · user-directed split **(workflow, S)** · front/back-matter classification **(both, M)** · pre-reparse edit-preservation **(workflow, M/L)**.

### 3.3 Speaker attribution & dialogue

**Where it breaks.** Attribution looks at *one atom of context* — no memory of who spoke last, no scene speaker-set. Pronoun tags ("she said") are discarded, not resolved. Ambiguous 2-person exchanges are only *flagged* (and only at 4+ consecutive lines) — never *resolved*; the common 2–3 line back-and-forth gets no help. Attribution can only point at already-discovered cast, and its `0.8` approval gate is disconnected from cast discovery's `0.72` create gate — a perfectly-parsed 0.93 line sits unresolved forever if the character got stuck in a *different* review queue. The LLM pass is sent orphaned lines *with the surrounding turns stripped out* — asked to solve turn-taking with the turns removed. The review UI is a flat card grid that reshuffles as you work, each card a 160-char snippet with no neighbors, no audio, no scene context.

**Flawless target.** Every line attributed to one speaker (named or explicit narrator/unknown, never a silent narrator default); rapid back-and-forth resolves from turn-taking; group scenes track a live speaker roster; interruptions/trailing-off stay attributed; confidence differentiated by rule type; uncertainty rare and self-evidently worth a human's time; **one human fix resolves the pattern.**

**Algorithm path.** A turn-taking/alternation model for 2-speaker exchanges (the single biggest win — resolves the class currently only flagged). Recency+gender pronoun coreference (reclaims a large, currently-100%-discarded class). Broader speech-verb/vocative/action-beat cues. Propagation of a confirmed attribution to identical/adjacent lines. Let attribution **propose new speakers back to cast discovery** (close the one-way pipeline). Per-scene active speaker sets. Calibrated rule-specific confidence (auto-approve colon/tag matches at a lower bar; be conservative on inference); reconcile the two thresholds. Give the LLM a contiguous scene window + few-shot from confirmed lines.

**Workflow/UX.** **A scene-level dialogue transcript view** — narration in gray, each line color-coded by speaker (colors reused across the whole app), in manuscript order — replacing the flat grid. This is the highest-leverage change: it lets a human do in one glance what today needs cross-referencing two screens. One-click reassign that offers "apply to the rest of this exchange." Bulk-approve high-confidence; surface only genuine ambiguity. Fix queue ordering to manuscript order (not `updated_at desc`). Inline per-line audio. Keyboard triage (number keys = scene's active speakers, j/k to move).

**Priorities:** scene transcript view **(workflow, M)** · turn-taking model **(algorithm, M)** · confirmation propagation **(both, S)** · reconcile the two confidence gates + re-trigger on cast change **(algorithm, S)** · pronoun coreference **(algorithm, M)** · bulk-approve / surface-only-ambiguous **(workflow, S)**.

### 3.4 Voice casting & performance direction

**Where it breaks.** Casting is 100% manual string-matching — a `VoiceProfile` has no gender/age/accent, adding one means pasting a raw provider voice ID, and Kokoro's locale+gender-encoded IDs are discarded. Direction inference casefolds the *whole segment* and substring-matches (the word "now" → urgent), blind to character, speaker, scene, continuity, and even `segment_type`. And **even correct direction isn't transmitted**: managed Kokoro hardcodes `speed=1.0` (no `--speed` flag at all), XTTS never receives its style prompt, `pauseBeforeMs` is read by no adapter, and assembly uses two fixed pause constants regardless of a segment's own `pauseAfterMs`. Only Piper honors anything. No persistent model worker — XTTS reloads a multi-GB model per segment, making audition-driven iteration infeasible.

**Flawless target.** Distinct, trait-matched casting audibly separable from narrator and from other in-scene characters; per-character consistency across the whole book; context-aware emotion/pace/pause that *actually renders*; natural micro-pacing from punctuation + directed intent; genre-appropriate narrator tone; and complete honesty about the local-engine ceiling.

**Algorithm path.** *Sequence matters: fix transmission before smarter inference, or you just make the dishonesty more sophisticated.* First: add `--speed` to the Kokoro wrapper and thread `pace`; drive **inter-segment silence from resolved `pauseBeforeMs`/`pauseAfterMs` at assembly** (one code path makes pauses audible on every engine); stop XTTS claiming style support it lacks (wire real `speed`, or pick among pre-recorded reference clips per emotion); make the deterministic `_infer` dialogue/narration-aware via `segment_type`. Then: reuse the proven speaker-attribution LLM pipeline for **evidence-based direction inference with character-mood continuity** (batch per scene, pass speaker + previous direction). Parse Kokoro voice-ID facets → structured gender/locale; add optional facets to `VoiceProfile`; rank the casting dropdown by trait match. A **persistent local TTS worker** (models resident) is the precondition for fast auditioning.

**Workflow/UX.** Ranked "suggested voices" with one-click audition **playing the character's own dialogue** (not a generic sentence). A "cast lineup" that plays one line across all voices back-to-back to catch confusable voices (enforcing the Voice Bible's own contrast rule). Surface real per-engine capability inline ("pace won't be audible with this voice"). In Direction Studio: a "play with current direction" button, inferred-evidence display, controls grayed out per engine capability, **batch-apply direction by scene/mood**, and a scene emotional-arc mini-timeline to spot flatlined or whiplashing delivery.

**Priorities:** Kokoro `--speed` + thread pace **(algorithm, S)** · assembly-driven pauses from direction **(algorithm, S)** · honest per-engine capability UI **(workflow, S)** · fix XTTS false style claim **(algorithm, S)** · `segment_type`-aware inference **(algorithm, S)** · LLM evidence-based direction **(algorithm, M)** · persistent TTS worker **(algorithm, M)** · audition-first casting from trait facets **(workflow, M)**.

### 3.5 Audio production quality

**Where it breaks.** Every chapter is hardcoded to **16 kHz mono** and downsampled with **linear interpolation and no anti-aliasing filter** (`assembly.py:52-54, 406-441`) — telephone-grade with added aliasing, below the ACX 44.1 kHz baseline, permanently baked in. No loudness normalization, no true-peak limiting — the mix hard-clips at ±32767. Pauses are fixed constants (direction pacing discarded). No head/tail room tone (fails ACX outright). Ambience loops without crossfade (clicks); "ducking" is a static −6 dB, not sidechain. MP3 export embeds **no ID3 tags or cover** (metadata goes only to a sidecar JSON); M4B — the actual audiobook container — is blocked; no retail sample. The UI has no real waveform, meters, or mastering preview.

**Flawless target.** 44.1 kHz/16-bit masters; MP3 ≥192 kbps with embedded ID3 + cover; **M4B with chapter markers, metadata, and artwork** as the flagship; integrated loudness in the ACX window (−23…−18 LUFS) consistent ±0.5–1 LU chapter-to-chapter; true-peak ≤ −3 dBTP via a lookahead limiter; verified noise floor; direction-aware pacing + room tone; crossfaded ambience with real sidechain ducking; auto retail sample; and a QA scorecard on every export.

**Algorithm path.** 44.1 kHz pipeline with a band-limited resampler (ffmpeg `aresample=soxr` — ffmpeg is already a dependency — or `scipy`/`soxr`). Two-pass EBU R128 loudnorm + true-peak limiter as a discrete post-mix stage replacing the hard clip. Room-tone head/tail padding + a real silence-gap scanner. Wire `pauseAfterMs`/`pauseBeforeMs` into assembly. Equal-power ambience crossfades + envelope-follower ducking. M4B via ffmpeg FFMETADATA chapter blocks + cover mux. MP3 `-metadata` + APIC cover. Retail-sample export reusing the mastering chain. Re-measure LUFS/peak/noise on the *final* artifact into the manifest. Move mix/duck/crossfade math to numpy or ffmpeg `filter_complex` (the pure-Python per-sample path won't scale at 44.1 kHz).

**Workflow/UX.** A real waveform player with clickable segment markers; wire `ChapterTimeline` selection to seek the player; issue markers as colored ticks on the waveform; live LUFS/true-peak/clipping meters; an A/B "as-produced vs mastered" pre-export preview folded into the readiness panel; unified format/metadata/cover setup that makes clear the fields are *embedded*; a post-export QA scorecard (measured LUFS, true peak, pass/fail) turning export history into a confidence signal; a one-click retail-sample button.

**Priorities:** loudness normalization + true-peak limiter **(algorithm, M — the single biggest "sounds mastered" lift)** · 44.1 kHz + proper resampling **(algorithm, M)** · MP3 ID3 + cover **(algorithm, S)** · M4B with chapters/metadata **(algorithm, L)** · real audio QA metrics **(algorithm, M)** · direction-aware pacing **(algorithm, S)** · waveform player + timeline scrub **(workflow, M)**.

### 3.6 QA & the review/patch workflow

**Where it breaks.** QA is a checklist, not a listener: readiness is all metadata-level, and the only code touching audio bytes checks duration, a naive clip threshold, and "100% of bytes are zero" silence (effectively dead against real speech). Render/assembly telemetry is **faked** (`peak:0`, empty waveform, hardcoded `validation_report: passed`). None of the rulebook's promised checks (loudness bounds, pronunciation coverage, truncation, voice confusion) exist. Two structural trust holes (see P1): the **resolve trap** (a resolved check stays hidden even while still failing) and the **patch no-op** (fix never forces re-render). Patch also re-renders in the **narrator voice with default direction**, not the segment's actual cast voice — the fix can *introduce* wrong-speaker/wrong-emotion defects. Chapter review shows issues from other chapters; export blocking is project-wide, not per selected chapter.

**Flawless target.** "Ready" is a live fact; QA catches what actually ruins audiobooks (mispronunciation, wrong actor, monotone where text implies emotion, truncated TTS, loudness jumps, dead air, bad pacing); fixing a line is single-click, uses the right voice/direction, and auto-re-verifies with a before/after; every screen shows one ranked "do this next"; verification is jump-to-timestamp, never a full re-listen.

**Algorithm path.** Real peak/RMS/LUFS/true-peak → inter-segment loudness-consistency + chapter-bounds checks. RMS-sliding-window dead-air detection feeding the (currently fake) silence metadata. Duration-vs-text truncation heuristic (wpm model per provider). Pre-render **pronunciation-risk flagging** (NER + OOV scan cross-referenced against the pronunciation dict). **Local ASR word-match verification** (whisper.cpp/faster-whisper, fully local) diffing transcript vs text — the highest-value new detector, the only one that verifies the TTS *said the words*. Render-time speaker-voice consistency check (would have auto-caught the patch narrator-fallback bug). Cheap pitch/energy-variance flatness check as a warning tier. **Auto-resolution**: re-evaluate against the newest render and system-resolve issues that now pass.

**Workflow/UX.** Fix the resolve trap and the patch no-op (P1). Patch defaults to the segment's *actual* resolved voice/direction and offers "regenerate (forces a new take)". Automatic, visible after-patch loop: re-render → re-run the exact failing checks → before/after both playable with the changed metric shown → auto-resolve or say what's still wrong. Real waveform on issue cards with "play this issue" seeking to the timestamp. Severity-weighted, ranked readiness worklist with a "do this next" card. Inline "add pronunciation" from a flag. Scope chapter-issue filters and export blocking to the actual chapter/selection. Per-section (not global) busy/error state. A distinct "listened & approved" chapter attestation separate from "0 automated flags."

**Priorities:** fix resolve trap **(algorithm, M)** · make patch actually re-render **(algorithm, S)** · auto-resolve on passing re-render **(algorithm, M)** · patch uses real voice/direction **(both, S)** · real loudness/clipping metrics **(algorithm, M)** · local ASR word-match **(algorithm, L)** · fix chapter/export issue scoping **(workflow, S)** · jump-to-audio waveform **(workflow, M)**.

---

## 4. Unified roadmap

The six analyses independently converged on the same sequencing wisdom: **repair the loops and the honesty first, then upgrade the algorithms, then add the delighters.** Better detectors feeding a leaky resolve/patch loop just produce more issues that silently don't get fixed; smarter direction that never reaches the engine just makes the dishonesty more sophisticated.

### Phase 1 — Make the existing loop trustworthy (mostly S, highest ROI)
Restore the meaning of the words the product already uses.
- Fix the resolve trap; auto-resolve on passing re-render (P1).
- Make patch actually force a re-render; use the segment's real voice/direction (P1).
- Fix render ordering (add `created_at`; stop sorting by random UUID) so fixes reach export (P1; see code report).
- Wire direction pauses through assembly; add Kokoro `--speed`; show honest per-engine capability (P4).
- Scope chapter-issue filters and export blocking to the actual selection.
- Surface already-computed evidence as actionable triage cards for cast & speaker review (P3).

### Phase 2 — Raise the algorithmic quality of every stage (mostly M)
- Read DOCX/EPUB/TOC structure; broaden heading detection (P5).
- Nickname lexicon + fuzzy alias clustering + same-name disambiguation gate; gender/age/vocal fields.
- Turn-taking model + pronoun coreference + confirmation propagation for attribution.
- Loudness normalization + true-peak limiter + 44.1 kHz pipeline; real audio QA metrics.
- Evidence-based LLM direction inference with character-mood continuity; persistent TTS worker.
- The feedback loop (P2): confirmations propagate and become few-shot exemplars across cast/speaker/direction.

### Phase 3 — Publishable output & delightful workflow (M–L)
- M4B with chapter markers + MP3 ID3/cover + retail sample.
- Local ASR word-match verification (the definitive intelligibility gate).
- Scene-level dialogue transcript view; waveform player with jump-to-issue; batch-apply direction; audition-first casting.
- Front/back-matter classification, multilingual support, footnote routing, prosody-tuned segmentation.
- Unified "next best action" model across the whole shell (P6); "listened & approved" attestation.

---

## 5. The through-line

The recurring lesson across all six capabilities: **Echodraft already thinks harder than it acts.** It discovers characters, infers direction, computes evidence, tracks lineage, and defines a QA rulebook — then discards the file's own structure metadata, drops direction before the engine, fakes the telemetry, hides the evidence, and lets one stale click mean "ready" forever. The path to a flawless product is less about inventing new intelligence and more about **delivering the intelligence already present, honestly, and letting every human correction compound.** Do that, and the same architecture that produces today's rough alpha produces a publishable audiobook with a workflow that gets easier the more you use it.

---

*Companion document: [`deep-analysis-report.md`](deep-analysis-report.md) covers the code-correctness and engineering findings (render-ordering bug, concurrency, CI). This document is the product/algorithm/workflow lens; where they overlap (render ordering, direction transmission, stubbed QA), the two reach the same conclusions from different angles.*
