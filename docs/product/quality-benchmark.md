# Echodraft — Quality Benchmark: Sunday Suspense

**Date:** 2026-07-03
**Purpose:** replace the abstract word "flawless" with a concrete, decomposable reference
target. When the [vision](../analysis/product-vision-analysis.md) and
[gap analysis](../analysis/gap-analysis.md) say a capability should reach maturity **5**,
this document is what "5" means.

---

## Why a benchmark

"Flawless" is unmeasurable and invites either paralysis or false confidence. A production
that already exists — made by humans, at scale, from the same kind of source material —
is a far better yardstick. **Sunday Suspense** is that yardstick.

## What Sunday Suspense is

Sunday Suspense is the long-running Bengali audio-story program produced by **Radio Mirchi
(Mirchi 98.3 FM), Kolkata**. It adapts suspense, horror, thriller, and detective
literature — Satyajit Ray, Sharadindu Bandyopadhyay, Sunil Gangopadhyay, Premendra Mitra,
plus translated Poe, Conan Doyle, Christie, Lovecraft — into **multi-voice audio
dramatizations** with a cast of distinct voice actors, a background score, and ambient sound
design, mixed with restraint so the story stays legible. It is, in effect, a
human-produced instance of exactly what Echodraft aims to generate.

Using it as the benchmark keeps the target honest in both directions: it shows what
"great" sounds like, and it exposes which parts of "great" are reachable with today's
local models and which are not (see [§ Reachability](#reachability-what-the-benchmark-costs)).

---

## Decomposing the benchmark into scored dimensions

Each dimension below is something Echodraft's pipeline produces, phrased as the
Sunday-Suspense-grade target (maturity **5**). These map directly onto the capabilities and
cross-cutting principles in the [gap analysis](../analysis/gap-analysis.md).

| # | Dimension | Sunday-Suspense-grade target (= maturity 5) | Maps to |
|---|---|---|---|
| B1 | **Cast identification** | Every named speaker discovered, de-duplicated, and aliased before production; no character missed, none doubled. | Character detection; P5 |
| B2 | **Narrator / dialogue separation** | Narration and every quoted line correctly split and attributed to the right speaker; the handful of genuine ambiguities triaged, not silently guessed. | Speaker attribution; structure |
| B3 | **Voice distinctness** | Each character is instantly distinguishable by voice; narrator sits apart from the cast; casting fits character traits (gender/age/register). | Voice casting |
| B4 | **Performance / delivery** | Emotion, pacing, and emphasis match the moment — suspense reads as tension, not monotone — and the direction is *actually heard* in the render, not just recorded as metadata. | Performance direction; P4 |
| B5 | **Sound design & ambience** | Score and ambient SFX (rain, footsteps, room tone, stings) support the scene and are tastefully mixed *under* the dialogue — present but never masking the words. | Audio production; `light_cinematic` mode |
| B6 | **Mastering & delivery fidelity** | Publishable loudness and dynamics (broadcast-grade target), clean transitions and pauses, chapter-marked, tagged, in a distributable container. | Audio production quality |
| B7 | **Adaptation fidelity** | The audio faithfully represents the manuscript — nothing dropped, garbled, or hallucinated; verse/scripts/formatting preserved. | Structure; QA (ASR verification) |
| B8 | **Listener-grade QA** | What ships has been verified to *sound* right (not merely "no automated flag"); regressions are caught before export. | QA; P1 |

A capability scores **5** on the [gap-analysis rubric](../analysis/gap-analysis.md#1-method--maturity-rubric)
when its corresponding dimension here would be indistinguishable from a Sunday Suspense
episode to an ordinary listener.

---

## Reachability: what the benchmark costs

The benchmark also makes the [model-capability](../architecture/local-ai/) reality concrete.
Sunday Suspense's quality comes from two things local models do *not* yet match, and several
things they do. Splitting the benchmark this way turns "flawless" from a wish into a
tiering decision.

| Benchmark dimension | Reachable with today's local stack? | Notes |
|---|---|---|
| B1 Cast identification | **Yes** | Squarely an LLM-for-judgment task; even a modest local model with a review loop gets there. Gap is *adoption/sizing*, not capability. |
| B2 Narrator/dialogue separation | **Yes** | Same — comprehension, not synthesis. Bottleneck is the current heuristic-default path, not the ceiling. |
| B3 Voice distinctness | **Mostly** | Distinct *timbres* are achievable (multiple voices/clones); nuanced *acting range* per voice is limited. |
| B4 Performance / delivery | **Partial** | Local TTS (Kokoro/Piper/XTTS-v2) has limited fine-grained emotional control. Restraint hides this; theatrical direction exposes it. This is the frontier-vs-local gap. |
| B5 Sound design & ambience | **Yes** | Mixing/ambience is an ffmpeg + asset problem, not a model ceiling. |
| B6 Mastering & delivery fidelity | **Yes** | Loudness normalization, limiting, chaptering, tagging are deterministic DSP/packaging. |
| B7 Adaptation fidelity | **Yes** | Structure preservation + ASR round-trip verification; no premium model required. |
| B8 Listener-grade QA | **Yes** | Real measurement + ASR checks close the "checklist not listener" gap. |

**The one honest exception is B4 (and the acting half of B3):** expressive,
character-differentiated *performance* is where local open TTS trails frontier/commercial
engines, and that is precisely the trait Sunday Suspense's voice actors supply. Echodraft's
patch/review architecture is designed so imperfect renders become a good *deliverable*
through human-in-the-loop editing — but the raw performance ceiling is a real constraint.
The product answer is tiering, not pretense: keep local engines for drafting/preview, be
honest in the UI about what each engine can honor ([P4](../analysis/product-vision-analysis.md)),
and offer an **optional** premium/cloud render tier for final output for users who accept
leaving strict local-first. See the [roadmap](roadmap.md) for where this sequences.

---

## How to use this document

- **Scoring:** when the gap analysis assigns a maturity level, check it against the matching
  Bn dimension here rather than against the word "flawless."
- **Prioritization:** dimensions marked **Yes** above are earned by wiring, honesty, and
  DSP — high leverage, no model dependency. The **Partial** one (B4) is a strategic/tiering
  decision, not a bug to fix.
- **Definition of done for "publishable":** an exported chapter that would not sound out of
  place next to a Sunday Suspense episode on dimensions B1, B2, B5, B6, B7, B8 — and is
  honest, at the point of control, about the current B3/B4 ceiling.
