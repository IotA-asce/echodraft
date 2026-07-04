# Progress Tracker

Last updated: 2026-07-04

This tracker follows the roadmap in `docs/product/roadmap.md` and the gap register in `docs/analysis/gap-analysis.md`.

## Maintenance Rule

- Update this file in the same branch and commit whenever a roadmap/gap item is implemented, verified, deferred, or found to need additional scope.
- Do not mark an item complete unless code is implemented, relevant tests/lint/typecheck have passed or the limitation is recorded, docs are updated when behavior changed, and the branch has been committed, merged, and pushed.
- For partial work, keep the parent checklist item open and add dated notes under the item.
- Keep branch names in `branch_type/branch_name` format, for example `feat/g13-export-polish`.

## Current Delivery State

- [x] G7 evidence-backed parser/cast triage queues shipped on `feat/g7-evidence-triage-queues` and merged to `main`.
- [x] G13 export polish shipped on `feat/g13-export-polish`.
  - M4B export, tagged MP3 export, retail sample generation, QA scorecard, docs, API schema, and tracker updates are implemented and verified.

## Phase 0 - Trust Foundation

- [ ] G1: Time-ordered render/export selection and assembly revision guard.
  - Add or verify `created_at` on render/export tables.
  - Select latest render/export by time, not random UUID ordering.
  - Assert render revision matches segment revision during assembly.
  - Verify patched segments always reach exported chapters.
- [ ] G2: Patch workflow forces fresh re-render with actual resolved voice/direction.
  - Force patch renders to bypass stale cache.
  - Resolve segment voice from override, approved cast voice, then narrator fallback.
  - Resolve segment direction from override, saved direction, then project default.
  - Verify patch attempts create fresh audio and lineage.
- [ ] G3: Readiness resolve-trap fix.
  - Re-derive readiness from current artifacts.
  - Auto-resolve only when current checks pass.
  - Add distinct ignore or accept-risk state that can re-surface when evidence changes.
- [ ] G12: SQLite and CI hardening.
  - Enable WAL, foreign keys, and `busy_timeout`.
  - Bound the job executor.
  - Add render uniqueness guard where needed.
  - Keep tests, lint, typecheck, and schema drift checks required before merge.

## Phase 1 - Honesty And Compounding Loop

- [ ] G4: Direction controls honestly affect supported engines.
  - Transmit Kokoro speed or mark unsupported controls honestly.
  - Use per-segment pause fields in assembly.
  - Surface per-engine direction capability in the UI.
- [ ] G6: Human correction feedback loop compounds.
  - Propagate confirmed speaker/cast corrections to sibling or adjacent rows.
  - Persist confirmed merges, attributions, and directions as facts.
  - Reuse confirmed facts or few-shot examples in later detection passes.
- [x] G7: Evidence-backed review triage queues.
  - Parser Review combines warnings and cast-discovery issues.
  - Apply, reject duplicate, and dismiss actions are wired.
  - Backend apply-action endpoint resolves `merge_cast` and `confirm_cast`.
- [ ] G8: DOCX/EPUB structure metadata.
  - Read DOCX heading styles as chapter/section signals.
  - Read EPUB spine and TOC as structure signals.
  - Preserve format-derived evidence in parser review.

## Phase 2 - Publishable Audio

- [ ] G5: 44.1 kHz mastered audio pipeline.
  - Band-limited resampling to 44.1 kHz.
  - EBU R128 loudness normalization.
  - True-peak limiter.
  - Room-tone head/tail.
  - Honest degradation when FFmpeg is missing.
- [ ] G11: Real audio QA metrics feeding readiness.
  - Peak/RMS/LUFS/true-peak checks.
  - RMS dead-air detection.
  - Duration-vs-text truncation heuristic.
  - Readiness consumes real audio metrics.
- [x] G13: Export polish.
  - [x] Add M4B export path with chapter markers and audiobook metadata.
  - [x] Add MP3 metadata and optional embedded cover path.
  - [x] Add optional retail sample generation.
  - [x] Add export QA scorecard in manifest and API response.
  - [x] Add typed backend QA/domain schema instead of unstructured dict only.
  - [x] Update static OpenAPI spec for `includeRetailSample` and export `qa`.
  - [x] Clarify direct-output M4B entry/path in manifest or API contract.
  - [x] Expand FFmpeg integration coverage for MP3 + M4B + retail sample + QA.
  - [x] Update ExportPanel scorecard copy to pass/fail symbols and M4B-aware empty state.
  - [x] Run full validation.
  - [x] Commit, merge to `main`, and push.

## Phase 3 - Algorithmic Depth

- [ ] G9: Character disambiguation and fuzzy aliasing.
  - Add same-name disambiguation gate before merge.
  - Add nickname lexicon and fuzzy alias clustering.
  - Extract casting-relevant traits.
- [ ] G10: Speaker attribution depth.
  - Add turn-taking and alternation model.
  - Add pronoun/coreference support.
  - Let attribution propose new speakers back to the cast.
- [ ] G14: Casting traits and audition-first suggestions.
  - Add gender/age/accent facets where available.
  - Extract Kokoro voice-ID facets.
  - Rank voice suggestions by character traits.
  - Audition voices against character lines.
- [ ] G19: Persistent local TTS worker.
  - Keep local models resident.
  - Speed up auditioning.
  - Support evidence-based LLM direction workflows.
- [ ] G4 follow-on: Evidence-based LLM direction inference.
  - Use scene, character, and mood continuity evidence.
  - Preserve direction evidence for review.
- [ ] G16: Local ASR word-match verification.
  - Verify generated speech matches expected text.
  - Flag mispronunciation, dropped words, and truncation.
- [ ] G18: Structure depth.
  - Add multilingual detection.
  - Classify front/back matter.
  - Handle multi-paragraph dialogue and footnotes.
  - Improve prosody-tuned segmentation.

## Phase 4 - Workflow Experience

- [ ] G15: Scene-level dialogue transcript review.
  - Color-code speakers in transcript view.
  - Add waveform player with issue markers.
  - Jump from issue to exact audio moment.
- [ ] G17: Scoped issues/export blocking and ranked worklist.
  - Scope chapter issues to selected chapter(s).
  - Scope export blockers to selected export set.
  - Add severity-weighted readiness worklist.
  - Replace global busy/error with per-section state where needed.
- [ ] G20: Unified next-best action.
  - Merge workflow step rail and readiness worklist signals.
  - Rank actions by impact.
  - Deep-link each action to the exact control or audio moment.
  - Add listened-and-approved chapter attestation.

## Completion Estimate

- Roadmap items tracked: 20 gaps.
- Completed: 2 gaps.
- In progress: 0 gaps.
- Remaining: 18 gaps.
- Current approximate roadmap completion: 10% complete, 10% touched.
