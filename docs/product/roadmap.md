# Echodraft — Roadmap to a Flawless Product

**Date:** 2026-07-03
**Derived from:** [`gap-analysis.md`](../analysis/gap-analysis.md) (gap register G1–G20), which measures the current build against [`product-vision-analysis.md`](../analysis/product-vision-analysis.md). Engineering specifics: [`deep-analysis-report.md`](../analysis/deep-analysis-report.md).
**"Flawless" means:** [`quality-benchmark.md`](quality-benchmark.md) — the Sunday Suspense yardstick. Most benchmark dimensions are reachable with the local stack (they're closed by the phases below); the expressive-performance ceiling (dimension B4) is a tiering decision surfaced in Phase 2.

---

## Guiding strategy: multipliers before features

The gap analysis found the largest, cheapest-to-close gaps are the **cross-cutting multipliers** — trust (P1), the feedback loop (P2), honesty (P4), evidence surfacing (P3), and using signal already present (P5) — not the per-capability algorithms. Upgrading a capability's algorithm while those holes remain yields little *felt* improvement: the output still isn't trustworthy and the user's corrections still evaporate.

So the sequence is deliberate:

> **Make the trust signals true → be honest and make corrections compound → make the audio publishable → deepen each capability's algorithm → polish the workflow.**

Each phase leaves the product in a coherent, shippable state and creates the foundation the next phase's gains land on and are retained by.

```
Phase 0  Trust foundation      ──┐
Phase 1  Honesty & compounding ──┼─ multipliers (small effort, critical impact)
                                 │
Phase 2  Publishable audio     ──┤─ deliverable quality
Phase 3  Algorithmic depth     ──┤─ per-capability recall/precision
Phase 4  Workflow experience   ──┘─ effortless guided journey
```

---

## Phase 0 — Trust foundation
**Theme:** "ready / resolved / fixed" must be live facts, and the pipeline must reliably deliver what it computed. Nothing above matters until this holds.
**Gaps:** G1, G2, G3, G12.

| Work | Gap | Effort |
|---|---|:---:|
| Add `created_at` to render/export tables; select "latest" by time (or reuse the parent-chain walk) everywhere; assert render `revision` matches segment on assembly | G1 | M |
| Make patch force a fresh re-render (or key cache on an attempt id); patch uses the segment's **actual** resolved voice/direction, not narrator/default | G2 | S |
| Fix the resolve-trap: re-derive readiness from the current artifact; auto-resolve only on a passing re-render; "ignore/accept-risk" a distinct, re-surfacing state | G3 | M |
| SQLite hardening (WAL + `busy_timeout` + FK PRAGMA + render uniqueness constraint, bounded job executor); CI running tests/lint/typecheck + a schema-drift check | G12 | S–M |

**Exit criteria:** a patched segment always reaches the exported chapter; QA re-verifies automatically and "ready" can never be stale-true; concurrent jobs don't error or fork history; every merge is gated by CI.
**Enables:** all later phases — this is what makes their improvements observable and durable.

## Phase 1 — Honesty & the compounding loop
**Theme:** stop advertising no-ops, surface the intelligence already computed, and make every human correction pay forward.
**Gaps:** G4, G6, G7, G8.

| Work | Gap | Effort |
|---|---|:---:|
| Transmit direction to engines (Kokoro `--speed`; assembly-driven per-segment pauses; wire or honestly drop XTTS style); show real per-engine capability in Direction/Casting UI | G4 | S–M |
| Feedback loop: confirmations propagate to sibling/adjacent items; persist confirmed merges/attributions/directions as facts + few-shot exemplars reused in later LLM passes | G6 | M |
| Turn parser/cast/speaker review logs into one-click triage queues with the already-computed evidence attached | G7 | M |
| Read DOCX `Heading` styles + EPUB spine/TOC as chapter signals (fixes the most common structure failure for near-zero cost) | G8 | S–M |

**Exit criteria:** no control in the UI silently no-ops; a single confirmation resolves its siblings and improves subsequent auto-detection; reviewers act on evidence-rich cards, not text logs; well-formed DOCX/EPUB books structure correctly on import.
**Depends on:** Phase 0 (corrections must actually re-render and re-verify to be worth compounding).

## Phase 2 — Publishable audio
**Theme:** the deliverable meets real audiobook standards.
**Gaps:** G5, G11, G13.

| Work | Gap | Effort |
|---|---|:---:|
| 44.1 kHz pipeline with band-limited resampling; EBU R128 loudness normalization + true-peak limiter replacing the hard clip; room-tone head/tail | G5 | M |
| Real audio QA metrics (peak/RMS/LUFS/true-peak, RMS dead-air, duration-vs-text truncation) feeding readiness | G11 | M |
| M4B with chapter markers/metadata/cover; MP3 ID3 + embedded cover; auto retail sample; post-export QA scorecard | G13 | L |

**Exit criteria:** an export meets ACX-style loudness/peak targets, ships as a tagged, chapter-marked M4B (and tagged MP3), and carries a trustworthy QA scorecard.
**Depends on:** Phase 0 (G1 so the mastered render is the one exported); benefits from G11↔G5 sharing the analysis code.

## Phase 3 — Algorithmic depth per capability
**Theme:** robustness across the messy variety of real manuscripts; delivery that sounds directed.
**Gaps:** G9, G10, G14, G16, G18, G19.

| Work | Gap | Effort |
|---|---|:---:|
| Character: disambiguation gate before same-name merge; nickname lexicon + fuzzy alias clustering; casting-relevant trait extraction | G9 | M |
| Speaker: turn-taking/alternation model + pronoun coreference; attribution proposes new speakers back to cast | G10 | M |
| Casting: gender/age/accent facets (auto for Kokoro voice IDs) + trait-ranked audition-first suggestions | G14 | M |
| Persistent local TTS worker (models resident) — unlocks fast auditioning and evidence-based LLM direction | G19 | M |
| Evidence-based LLM direction inference with character-mood continuity (built on G19) | (G4 follow-on) | M |
| Local ASR word-match verification — the definitive intelligibility/mispronunciation gate | G16 | L |
| Structure depth: multilingual detection, front/back-matter classification, multi-paragraph dialogue, footnote routing, prosody-tuned segmentation | G18 | M–L |

**Exit criteria:** full cast discovered and correctly aliased without manual cleanup on typical books; dialogue attribution needs only a handful of human decisions; voices are distinct and trait-matched; QA catches mispronunciations and truncation; non-English and non-standard manuscripts parse correctly.
**Depends on:** Phases 0–1 (feedback loop + evidence queues make the review of these algorithms' output tractable); G19 precedes evidence-LLM direction and audition UX.

## Phase 4 — Workflow experience
**Theme:** the guided journey feels effortless and confidence-building.
**Gaps:** G15, G17, G20.

| Work | Gap | Effort |
|---|---|:---:|
| Scene-level color-coded dialogue transcript review view; jump-to-audio waveform player with issue markers | G15 | M |
| Scope chapter-issue filters and export blocking to the actual selection; severity-weighted readiness worklist; per-section (not global) busy/error state | G17 | S |
| Unified "next best action" across the shell (merge step-rail + readiness worklist into one ranked, deep-linked model); "listened & approved" chapter attestation | G20 | M |

**Exit criteria:** at every step the product shows the single highest-impact next action with one click to the exact control or audio moment; review of a chapter shows only that chapter's issues; "complete" reflects a human decision, not just absence of automated flags.
**Depends on:** Phases 1–3 (the transcript view and worklist are most valuable once attribution/QA produce trustworthy, evidence-rich output).

---

## Sequencing & dependencies at a glance

| Phase | Primary value | Blocking prerequisites |
|---|---|---|
| 0 Trust foundation | Makes all signals/outputs trustworthy | — |
| 1 Honesty & loop | Stops no-ops; corrections compound | Phase 0 |
| 2 Publishable audio | Deliverable meets standards | Phase 0 (G1) |
| 3 Algorithmic depth | Robust on real manuscripts | Phases 0–1; G19 before evidence-LLM direction |
| 4 Workflow experience | Effortless guided journey | Phases 1–3 |

Phases 1 and 2 are largely independent and can run in parallel once Phase 0 lands. Phase 4's polish should trail the capability work it presents.

## Success metrics (per phase)

- **Phase 0:** 0 cases where a patched segment is excluded from export; readiness never reports "ready" while a check still fails; 0 `database is locked` errors under concurrent jobs; CI green required to merge.
- **Phase 1:** 0 UI controls that silently no-op; a confirmed correction measurably reduces the remaining review queue; import of standard DOCX/EPUB yields correct chapters with no manual boundary fixes.
- **Phase 2:** exports pass an automated ACX-style loudness/true-peak check; M4B opens with correct chapters/metadata in a standard player.
- **Phase 3:** cast/attribution/QA require only spot human review on a representative test corpus; non-English sample parses correctly.
- **Phase 4:** a new user completes import→export on a sample book guided solely by the "next best action" prompts.

## Guardrails (carry through every phase)

Per [`AGENTS.md`](../../AGENTS.md) and [`CLAUDE.md`](../../CLAUDE.md): segment stays the atomic unit; render history stays append-only; no audio blobs in the DB; local-first (no cloud-only assumptions); update manifests when pipeline I/O changes; branch → verify → merge → push for every change.
