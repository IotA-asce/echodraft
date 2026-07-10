# Progress Tracker

Last updated: 2026-07-07

This tracker follows `docs/product/roadmap.md` and `docs/analysis/gap-analysis.md`.

## Maintenance Rule

- Update this file in the same branch and commit whenever a roadmap or gap item is implemented, verified, deferred, or changes status.
- Do not mark an item complete unless code is implemented, relevant validation passed or the limitation is recorded, docs were updated if behavior changed, and the work was committed, merged, and pushed.
- For partial work, keep the parent item unchecked and add dated notes under it.
- Branch names must use `branch_type/branch_name`, for example `feat/render-ordering`, `fix/readiness-refresh`, or `chore/update-progress-tracker`.

## Status Summary

- Numbered gaps tracked: 20
- Complete: 20
- Remaining: 0
- In progress: 0
- Approximate roadmap completion: 100%
- Complete phases: Phase 0, Phase 1, Phase 2, Phase 3, Phase 4
- Remaining phases: None

## Recently Shipped

- [x] Phase 0 trust foundation shipped.
  - Evidence: `feat/g1-render-ordering` (`033839c`, merged `dce8b2e`), `feat/g2-patch-rerender` (`e1cb74a`, `f9a3cf6`, merged `a8dc529`), `feat/g3-readiness-resolve` (`5f41339`, `b47ca4c`, merged `6416f91`), and `feat/g12-db-hardening-ci` (`f7fabde`, merged `bc0a932`).
- [x] Phase 1 honesty and compounding loop shipped.
  - Evidence: `feat/g4-direction-transmission` (`e8d63aa`, `c7beca5`, merged `fb736fe`), `feat/g8-container-chapter-signals` (`e04bacf`, `6f387c8`, merged `c6d4331`), `feat/g6-feedback-loop-complete` (`977a9bd`, merged `9d32904`), and `feat/g7-evidence-triage-queues` (`b4237c0`, merged `b0b0bde`).
- [x] Phase 2 publishable audio shipped.
  - Evidence: `feat/g11-real-audio-qa` (`ef42a32`, `df1e332`, merged `d8e7cad`), `feat/g5-mastered-audio` (`5d3ad3f`, merged `3dedf83`), and `feat/g13-export-polish` (`7f27089`, merged `66fcf7a`).
- [x] G14 casting traits and audition-first suggestions shipped.
  - Evidence: `feat/phase-3-cast-depth`, `feat/g14-voice-facets-auditions`.
- [x] G10 speaker attribution depth shipped.
  - Evidence: `feat/phase-3-cast-depth`, `feat/g10-speaker-attribution-depth`, `feat/g10-scene-window-attribution`, `feat/g10-active-speaker-model`.
- [x] G19 persistent local TTS worker shipped.
  - Evidence: `feat/g19-persistent-tts-worker`; documented in `docs/pipeline/tts/tts-production-upgrade.md`.
- [x] Direction follow-on evidence-based LLM inference shipped.
  - Evidence: `feat/evidence-based-direction-inference`; documented in `docs/pipeline/direction/direction-studio.md`.
- [x] G16 local ASR word-match verification shipped.
  - Evidence: `feat/g16-local-asr-word-match`; documented in `docs/pipeline/qa/qa-rulebook.md`.
- [x] G18 structure depth shipped.
  - Evidence: `feat/g18-structure-depth`; documented in `docs/pipeline/structure/structure-parser-v2.md`.
- [x] G15 scene-level transcript review shipped.
  - Evidence: `feat/g15-transcript-review`; documented in `docs/pipeline/review/review-patch-workbench.md`.
- [x] G17 scoped issues, export blocking, and ranked worklist shipped.
  - Evidence: `feat/g17-scoped-worklist`; documented in `docs/pipeline/qa/readiness-qa.md` and `docs/pipeline/export/export-polish.md`.
- [x] G20 unified next-best action shipped.
  - Evidence: `feat/g20-next-best-action`; documented in `docs/pipeline/review/review-patch-workbench.md` and `docs/pipeline/qa/readiness-qa.md`.

## Phase 0 - Trust Foundation

- [x] G1 - Render/export ordering and assembly determinism.
  - [x] Add or verify deterministic `created_at` ordering for renders and exports.
  - [x] Select latest render/export by `created_at DESC, id DESC`.
  - [x] Guard assembly against stale manuscript or segment revisions.
  - Evidence: `033839c`; documented in `docs/architecture/current-pipeline-behavior.md`.
- [x] G2 - Patch rerender correctness.
  - [x] Force fresh renders for patched segments instead of reusing stale audio.
  - [x] Resolve voice and direction during patch rerenders.
  - [x] Store render lineage through `parent_render_id`.
  - Evidence: `e1cb74a`, `f9a3cf6`; documented in `docs/pipeline/review/review-patch-workbench.md`.
- [x] G3 - Readiness checks rederive current state.
  - [x] Recompute readiness from current parser, QA, render, and export state.
  - [x] Auto-resolve checks fixed by later work.
  - [x] Re-surface accepted risk when underlying evidence changes.
  - Evidence: `5f41339`, `b47ca4c`, `f70edca`.
- [x] G12 - Local database and worker hardening.
  - [x] Enable SQLite WAL, foreign keys, and busy timeout.
  - [x] Bound executor and job concurrency.
  - [x] Serialize segment-render cache recheck, parent selection, and insert with a SQLite write transaction.
  - [x] Add CI with schema drift checking.
  - Evidence: `f7fabde`, `feat/phase-0-completion`.

## Phase 1 - Honesty And Compounding Loop

- [x] G4 - Direction transmission into audio.
  - [x] Transmit supported pace controls to managed Kokoro/Piper render paths.
  - [x] Honor `pauseBeforeMs` and `pauseAfterMs` during assembly.
  - [x] Expose truthful engine capability metadata instead of implying unsupported controls.
  - Evidence: `e8d63aa`, `c7beca5`; documented in `docs/pipeline/direction/direction-studio.md` and `docs/pipeline/tts-production-upgrade.md`.
- [x] G6 - Feedback loop compounds speaker and cast corrections.
  - [x] Persist confirmed same-speaker assignments.
  - [x] Persist cast merge decisions.
  - [x] Reuse confirmed cast facts in later parser and attribution passes.
  - Evidence: `977a9bd`; documented in `docs/pipeline/casting/speaker-attribution.md` and `docs/pipeline/casting/character-bible.md`.
- [x] G7 - Parser and cast evidence triage queues.
  - [x] Parser Review combines parser warnings and cast-discovery issues.
  - [x] Apply, reject, and dismiss actions are wired.
  - [x] Backend apply-action endpoint supports merge-cast and confirm-cast actions.
  - Evidence: `b4237c0`.
- [x] G8 - Container-derived chapter signals.
  - [x] Parse DOCX heading-style signals.
  - [x] Parse EPUB spine and table-of-contents signals.
  - [x] Persist structure evidence in Parser Review.
  - Evidence: `e04bacf`, `6f387c8`; documented in `docs/pipeline/structure/structure-parser-v2.md`.

## Phase 2 - Publishable Audio

- [x] G5 - Mastered audio baseline.
  - [x] Use a 44.1 kHz assembly pipeline.
  - [x] Apply band-limited resampling.
  - [x] Normalize loudness and apply a true-peak limiter.
  - [x] Insert calibrated room tone for natural pauses.
  - Evidence: `5d3ad3f`; documented in `docs/architecture/current-pipeline-behavior.md` and `docs/pipeline/audio/sound-design.md`.
- [x] G11 - Real audio QA replaces fake telemetry.
  - [x] Decode rendered audio and collect real metrics.
  - [x] Detect dead air, clipping, truncation, loudness, and duration anomalies from audio content.
  - [x] Feed real QA metrics into readiness.
  - Evidence: `ef42a32`, `df1e332`; documented in `docs/pipeline/qa/qa-rulebook.md`.
- [x] G13 - Export polish for listener and retail artifacts.
  - [x] Generate M4B chapterized export.
  - [x] Generate MP3 exports with metadata and cover art.
  - [x] Generate retail sample clips.
  - [x] Add QA scorecard, typed export schema, OpenAPI coverage, and artifact URLs.
  - Evidence: `7f27089`; documented in `docs/pipeline/export/export-polish.md`.

## Phase 3 - Algorithmic Depth

- [x] G9 - Character disambiguation and fuzzy aliasing.
  - [x] Add disambiguation gate before same-name character merges.
  - [x] Add fuzzy spelling-variant duplicate review.
  - [x] Add initial title/nickname alias enrichment.
  - [x] Extract conservative casting-relevant character traits from observed evidence.
  - Evidence: `feat/phase-3-cast-depth`, `feat/g9-disambiguation`; documented in `docs/pipeline/casting/character-bible.md`.
- [x] G10 - Speaker attribution depth.
  - [x] Add initial nearby-turn and pronoun-cue evidence for unlabeled dialogue.
  - [x] Add conservative two-speaker alternation for same-scene unlabeled dialogue.
  - [x] Add broader speech-action cue and gendered pronoun coreference support.
  - [x] Let attribution propose confident missing speaker labels back through Cast Discovery.
  - [x] Expand into full scene active-speaker and interruption model.
  - [x] Send contiguous scene windows to the LLM attribution pass.
  - Evidence: `feat/phase-3-cast-depth`, `feat/g10-speaker-attribution-depth`, `feat/g10-scene-window-attribution`, `feat/g10-active-speaker-model`; documented in `docs/pipeline/casting/speaker-attribution.md`.
- [x] G14 - Casting traits and audition-first suggestions.
  - [x] Add initial gender, age, accent, and role traits where directly observed.
  - [x] Extract Kokoro voice-ID facets.
  - [x] Rank existing project voice suggestions by character traits.
  - [x] Audition voices against representative character lines.
  - Evidence: `feat/phase-3-cast-depth`, `feat/g14-voice-facets-auditions`; documented in `docs/pipeline/casting/character-bible.md`.
- [x] G19 - Persistent local TTS worker.
  - [x] Keep local models resident.
  - [x] Speed up auditioning.
  - [x] Enable evidence-based LLM direction workflows.
  - Evidence: `feat/g19-persistent-tts-worker`; managed Kokoro ONNX now uses a resident JSON worker and exposes worker status at `GET /api/v1/settings/tts/worker`.
- [x] Direction follow-on - Evidence-based LLM direction inference.
  - [x] Use scene, character, and mood continuity evidence.
  - [x] Preserve direction evidence for review.
  - Evidence: `feat/evidence-based-direction-inference`; deterministic inference remains default, optional local LLM direction rows persist `evidence_json`, and locked rows remain protected.
  - Note: this is not counted as a separate G1-G20 gap, but remains a roadmap follow-on after G4 and depends on G19.
- [x] G16 - Local ASR word-match verification.
  - [x] Verify generated speech matches expected text.
  - [x] Flag mispronunciation, dropped words, and truncation.
  - [x] Feed ASR verification evidence into QA and readiness.
  - Evidence: `feat/g16-local-asr-word-match`; optional whisper.cpp-compatible ASR writes render metadata, opens review warnings, and feeds readiness when configured.
- [x] G18 - Structure depth.
  - [x] Add multilingual detection.
  - [x] Classify front matter and back matter.
  - [x] Handle multi-paragraph dialogue and footnotes.
  - [x] Improve prosody-tuned segmentation.
  - Evidence: `feat/g18-structure-depth`; parser quality exposes detected language, chapter evidence records language and matter type, multi-paragraph dialogue remains dialogue, footnotes route to review, and long narration uses clause-aware prosody splitting.

## Phase 4 - Workflow Experience

- [x] G15 - Scene-level dialogue transcript review.
  - [x] Color-code speakers in transcript view.
  - [x] Add waveform player with issue markers.
  - [x] Jump from issue to exact audio moment.
  - Evidence: `feat/g15-transcript-review`; active chapter review timeline uses manifest segment offsets, speaker colors, waveform markers, and issue deep links.
- [x] G17 - Scoped issues, export blocking, and ranked worklist.
  - [x] Scope chapter issues to selected chapters.
  - [x] Scope export blockers to the selected export set.
  - [x] Add severity-weighted readiness worklist.
  - [x] Replace global busy/error with per-section state where needed.
  - Evidence: `feat/g17-scoped-worklist`; readiness and export preflight now respect selected chapter scope, and the dashboard surfaces ranked findings plus export blockers.
- [x] G20 - Unified next-best action.
  - [x] Merge workflow step rail and readiness worklist signals.
  - [x] Rank actions by impact.
  - [x] Deep-link each action to the exact control or audio moment.
  - [x] Add listened-and-approved chapter attestation.
  - Evidence: `feat/g20-next-best-action`; shell actions merge workflow, readiness, export, timeline, and approval signals, and chapter approvals are tied to active chapter renders.

## Completion Estimate

- Roadmap items tracked: 20 numbered gaps.
- Completed: 20 numbered gaps.
- In progress: 0 numbered gaps.
- Remaining: 0 numbered gaps.
- Approximate roadmap completion: 100%.
- Phase completion: Phase 0 100%, Phase 1 100%, Phase 2 100%, Phase 3 100%, Phase 4 100%.

## v2 Program Tracker

This section tracks the v2 roadmap in
[`docs/plans/2026-07-07-v2-implementation-roadmap.md`](plans/2026-07-07-v2-implementation-roadmap.md).
It is separate from the completed G1-G20 alpha gap tracker above.

### Phase A - Fast Automatic Pipeline

- [x] W1 - Eval baseline harness.
  - [x] W1.1 - Golden corpus fetch/seed script.
  - [x] W1.2 - Attribution and cast metrics module.
  - [x] W1.3 - Baseline report harness and recorded baseline.
- [x] W2 - Orchestrator core.
  - [x] W2.1 - Orchestrator package alongside the old runner.
  - [x] W2.2 - Event bus and SSE endpoint.
  - [x] W2.3 - Inference cache and provider abstraction.
  - [x] W2.4 - Adaptive LLM worker pool and hardware probe.
  - [x] W2.5 - audio-gen and tts pool seams.
- [x] W3 - Extraction v2.
  - [x] W3.1 - Parallelize existing LLM loops.
  - [x] W3.2 - Ingestion v2.
  - [x] W3.3 - Structure v2.
  - [x] W3.4 - Cast v2.
    - Evidence: `feat/cast-v2-clustering`; feature-flagged constrained alias clustering batches
      local embeddings, respects cannot-link and durable merge rulings, reconciles once per
      cluster, synthesizes W4-ready profiles, and records additive manifest diagnostics.
    - Gate: cast precision/recall/F1 and alias purity remained 1.0, merge/split error rates
      remained 0, and flags fell from 3 to 2 on `modern-format-synthetic`; see
      `docs/analysis/eval-baselines/2026-07-10-cast-v2-gate.md`.
  - [x] W3.5 - Attribution v2.
    - Evidence: `feat/attribution-v2-llm-primary`; feature-flagged scene-window MAP treats the
      deterministic cascade as candidate evidence, carries conversation state, votes three times
      on low-confidence targets, and performs a bounded alternation reduce without touching locks.
    - Gate: attribution accuracy, auto-accept precision, attributable-dialogue recall, and explicit
      speaker coverage remained 1.0; see
      `docs/analysis/eval-baselines/2026-07-10-attribution-v2-gate.md`.
  - [x] W3.6 - Confidence and flag model.
    - Evidence: `feat/extraction-flag-model`; migration `0032` adds auditable decision tiers and
      durable grouped review tasks, with open-cause deduplication and typed list/status APIs.
    - Gate: the committed fixture produces 2 optional grouped tasks, 0 required tasks, and retains
      1.0 attribution accuracy/precision/recall; see
      `docs/analysis/eval-baselines/2026-07-10-confidence-v2-gate.md`.
  - [x] W3.7 - Direction v2 and progressive delivery.
    - Evidence: `feat/direction-v2-progressive`; profile-aware scene windows refine in parallel,
      while chapter-priority checkpoints/events publish provisional directions during the first pass.
    - Gate: the committed fixture emitted its first chapter-ready event in 0.029 s with 1 optional
      grouped task and 0 required tasks; the 500-page hardware milestone remains a separate M1/M2
      acceptance run. See `docs/analysis/eval-baselines/2026-07-10-direction-v2-gate.md`.
- [x] W4 - Automatic casting.
  - [x] W4.1 - Voice catalog and one-time audition backfill.
    - Evidence: `feat/voice-catalog`; migration `0033` adds versioned global catalog entries and
      voice-profile links, while the idempotent audition job stores WAVs on disk and persists local
      acoustic measurements, provenance, license metadata, and measured facets.
  - [x] W4.2 - Narrator selection.
    - Evidence: `feat/casting-narrator-selection`; ordered narration drives a first-person-pronoun
      ratio sanity check, commercially usable measured voices are ranked deterministically, and
      reruns reuse the persisted catalog-linked narrator profile.
  - [x] W4.3 - Scoring and constraint-solving assignment.
    - Evidence: `feat/casting-solver`; migration `0034` adds append-only casting decisions and
      automatic-casting settings. The deterministic solver derives dialogue prominence and scene
      co-occurrence, reserves the narrator, enforces required facets and major uniqueness, scores
      timbre/reuse/distinctiveness, and routes sub-floor walk-ons intentionally to the narrator.
  - [x] W4.4 - Auto-chain, override model, and backward compatibility.
    - Evidence: `feat/casting-autochain`; migration `0035` links automatic assignments to their
      decisions and locks legacy hand-cast rows. The v2 extraction chain casts after attribution,
      preserves locked narrator/character choices, blocks accidental narrator reuse, and writes a
      versioned casting manifest while keeping ranked decision alternatives inspectable.

- [ ] W5 - Expressive TTS.
  - [x] W5.1 - Device-aware multi-worker engine host.
    - Evidence: `feat/tts-engine-host`; the provider-neutral resident host dispatches N workers
      through the bounded TTS pool, reports device/worker state, shuts down cleanly, and lets XTTS
      use the hardware-probed CPU/CUDA/MPS device instead of forcing CPU.
  - [x] W5.2 - Tier-A direction compiler.
    - Evidence: `feat/direction-compiler`; a pure compiler now maps managed Kokoro pace and Piper
      pace/sentence silence while preserving the existing effective/unsupported direction contract
      exactly for custom Kokoro, Piper, managed Kokoro, and XTTS.
  - [ ] W5.3 - Tier-S bake-off and selection.
    - Harness ready: `feat/tts-bakeoff`; the fixed eight-script scorer, R10/R13 hard gates, current
      hardware/runtime preflight, and fail-closed selector are implemented. The recorded M4 run has
      no installed candidate runtime, so no engine is selected without explicit Model Center
      download/license consent and blind ratings.
  - [ ] W5.4 - Selected Tier-S integration and voice identities.
  - [ ] W5.5 - Expressive mappings and ASR-gated retry.
  - [ ] W5.6 - New-voice synthesis and consent-gated cloning.

### v2 Remaining Phases

- [ ] Phase B - Expressive TTS and generative sound.
- [ ] Phase C - Minimal monochrome UI.
- [ ] Phase D - Desktop packaging.
- [ ] Phase E - Mobile.
