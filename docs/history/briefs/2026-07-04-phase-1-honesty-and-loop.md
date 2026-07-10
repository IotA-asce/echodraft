# Phase 1 — Honesty & the Compounding Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close gaps G4, G8, G6, G7 from [`docs/history/analysis/gap-analysis.md`](../analysis/gap-analysis.md) per [`docs/product/roadmap.md`](../../product/roadmap.md) Phase 1: no UI control silently no-ops, well-formed DOCX/EPUB books structure correctly, corrections propagate and teach, and reviewers act on evidence-rich queues instead of text logs.

**Architecture:** Four sequential tasks (stream A), each on its own feature branch off latest `main`, merged `--no-ff` and pushed after task review. Runs in parallel with the Phase 2 stream (separate plan); Task A1 must merge before Phase 2's G5 task starts (both touch `assembly.py`).

**Tech Stack:** Python 3.12/FastAPI/SQLAlchemy/Alembic, Pydantic v2, python-docx + ebooklib (already deps), Next.js/TypeScript.

## Global Constraints

Same as Phase 0 plan (`2026-07-03-phase-0-trust-foundation.md` Global Constraints) — branch/verify/merge/push discipline, append-only history, no blobs in DB, migration + `_repair_sqlite_schema_drift` pairing for every schema change (next free migration number after Phase 0 = check `libs/db/alembic/versions/` at branch time), mypy strict, ruff, tests in `apps/api/tests/`, docs updated with behavior. CI now exists (`.github/workflows/ci.yml`) — after each merge, confirm the run is green (`gh run list --branch main`).

---

### Task A1 (G4): Transmit direction to engines; honest capability everywhere

**Branch:** `feat/g4-direction-transmission`

**Problem (all confirmed at file:line):** `ManagedKokoroOnnxAdapter` reports `effectiveDirection: {pace}` but its generated wrapper hardcodes `kokoro.create(..., speed=1.0)` (`kokoro_setup.py:419`, argparse at :394-403 has no `--speed`); the adapter command (tts_providers.py:230-245) passes no speed either. Custom `KokoroTtsAdapter` (tts_providers.py:101-167) claims `{pace}` with no CLI contract to send it. `XttsV2Adapter` claims `{stylePrompt}` but `tts.tts_to_file(...)` (:384-390) has no style parameter. Assembly ignores `pauseBeforeMs`/`pauseAfterMs`: fixed constants 350/800 ms (assembly.py:55-56) applied in `_write_speech_stem` (:246-270), even though `_resolve_inputs` already parses each render's `request_json` (:230) which contains the full direction. `_unsupported_direction`'s `all_controls` (tts_providers.py:440-451) omits `stylePrompt`/`noSfx`. The UI never shows per-engine capability: `/api/v1/settings/tts/providers` already returns `capabilities.direction` per provider (tts_providers.py:30-46) but `ProviderStatus.tsx:3-18` ignores it and `DirectionControls.tsx` renders identical sliders for every engine.

**Files:**
- Modify: `apps/api/src/echodraft_api/kokoro_setup.py` (WRAPPER_SOURCE: `--speed` arg + `speed=args.speed`; wrapper self-heal, see step 2)
- Modify: `apps/api/src/echodraft_api/tts_providers.py` (managed-Kokoro `--speed` pass-through; custom Kokoro `direction_support` → `set()`; XTTS `direction_support` → `set()` and drop the fake stylePrompt echo; `_unsupported_direction` all_controls += {"stylePrompt", "noSfx"})
- Modify: `apps/api/src/echodraft_api/assembly.py` (`_write_speech_stem` + `_resolve_inputs`: per-segment pauses; manifest `pauses` block gains per-segment applied values)
- Modify: `apps/web/app/components/setup/ProviderStatus.tsx` (render `capabilities.direction` list) and `apps/web/app/components/structure/DirectionControls.tsx` (accept a `supportedDirection: string[] | null` prop; visually mark unsupported controls "not honored by current engine" — disable is too strong since renders can switch engine later; annotate)
- Modify: `apps/web/app/project-dashboard.tsx` (thread active provider's `capabilities.direction` into DirectionControls via its parent `SegmentEditorCard.tsx`)
- Modify docs: `docs/pipeline/direction/direction-studio.md`, `docs/pipeline/tts/tts-production-upgrade.md` (real capability matrix), `docs/architecture/current-pipeline-behavior.md` (pause behavior)
- Test: `apps/api/tests/test_assembly.py` (per-segment pause), `apps/api/tests/test_tts_production_upgrade.py` (capability contract), `apps/api/tests/test_kokoro_setup.py` (wrapper regeneration + --speed)

**Interfaces:**
- Produces: assembly honors `direction.pauseBeforeMs`/`pauseAfterMs` per segment — rule: pause inserted between segments = `max(prev.pauseAfterMs, next.pauseBeforeMs, default_gap)` where `default_gap` is the existing 350/800 constants (scene boundary keeps 800 floor); values come from the render's `request_json["direction"]` (the direction that actually rendered). Kokoro managed renders receive `--speed {pace:.3f}`. Provider `capabilities.direction` is truthful: managed Kokoro `{pace}`, Piper `{pace, pauseAfterMs}` + now `pauseBeforeMs`/`pauseAfterMs` honored by assembly for all engines (declare `pauseBeforeMs`/`pauseAfterMs` in every real provider's `direction_support` since assembly now honors them engine-independently), custom Kokoro `∅`, XTTS `∅`, Mock unchanged (test double).
- Consumes: Phase 0's `created_at` ordering (no interaction beyond rebase).

**Steps:**

- [ ] **Step 1 (RED): assembly pause test.** In `test_assembly.py`: produce a 2-segment chapter via mock provider where segment 1's saved direction has `pauseAfterMs: 1200` (save via the segment-direction PUT endpoint before producing). Assert assembled `durationMs` ≥ sum(segment durations) + 1200 (not + 350). Run — fails (fixed 350 used).
- [ ] **Step 2: wrapper `--speed` + self-heal.** Add `--speed` argparse arg (default 1.0) to `WRAPPER_SOURCE` and pass `speed=args.speed` to `kokoro.create`. Existing installs have the old wrapper on disk: make `ManagedKokoroOnnxAdapter` (or the setup service that resolves `wrapper_path`) rewrite the wrapper file whenever its content differs from the current `WRAPPER_SOURCE` (it is generated content; find where wrapper_path is created in kokoro_setup.py and add an idempotent refresh used at adapter construction/validation). Test: write a stale wrapper file, construct the adapter/run validation, assert file now matches `WRAPPER_SOURCE` (follow `test_kokoro_setup.py` monkeypatch patterns; no real kokoro install).
- [ ] **Step 3: adapter transmits pace.** `ManagedKokoroOnnxAdapter.preview` appends `["--speed", f"{direction.pace:.3f}"]`. `effectiveDirection` stays `{pace}` — now true.
- [ ] **Step 4: honesty downgrades.** Custom `KokoroTtsAdapter.direction_support = set()` (no CLI contract exists — document in class docstring); remove its `effectiveDirection` pace echo. `XttsV2Adapter.direction_support = set()`; remove the stylePrompt echo. Add `"stylePrompt"`, `"noSfx"` to `_unsupported_direction.all_controls`. Update every real provider's `direction_support` to include `"pauseBeforeMs", "pauseAfterMs"` (honored engine-independently by assembly after step 5).
- [ ] **Step 5: assembly per-segment pauses.** In `_resolve_inputs`, extract `(pause_before_ms, pause_after_ms)` from the same parsed `request_json` used for the revision check; carry on `AssemblyInput`. In `_write_speech_stem`, between consecutive items use `max(prev.pause_after_ms, next.pause_before_ms, scene_or_paragraph_default)`. Clamp to the DirectionProfile bounds (0–5000). Record actually-applied per-gap values in the manifest (`"pauses": {"paragraphMs":..., "sceneMs":..., "applied": [{"afterSegmentId":..., "ms":...}]}`).
- [ ] **Step 6 (GREEN + more tests):** step-1 test passes. Add: capability contract test (GET providers; assert managed-kokoro lists exactly `{pace, pauseBeforeMs, pauseAfterMs}` sorted, xtts/custom-kokoro list only the pause fields, i.e. no fake claims); a managed-kokoro command test (monkeypatch subprocess, assert `--speed` present, following existing kokoro test style).
- [ ] **Step 7: frontend.** ProviderStatus renders the active provider's honored direction controls ("Honors: pace, pauses"). DirectionControls takes `supportedDirection` and annotates unsupported controls with a "not honored by current engine" hint. `npm run web:lint`, `npm run web:typecheck`.
- [ ] **Step 8: full battery, docs, commit `feat(direction): transmit pace and per-segment pauses; truthful engine capability`, merge `--no-ff`, push, check CI green.**

---

### Task A2 (G8): DOCX heading styles + EPUB spine/TOC as chapter signals

**Branch:** `feat/g8-container-chapter-signals`

**Problem:** `ingestion.py:237-241` reduces DOCX to `p.text` (never reads `paragraph.style.name`); `ingestion.py:242-256` flattens EPUB items in manifest order, ignoring `book.spine` (reading order) and `book.toc` entirely. Chapter detection then requires literal English keywords (`EXPLICIT_CHAPTER_RE`, structure_parsing.py:36-41); `chapter_candidates()` (structure_parsing.py:424-464) skips even markdown headings that don't match the regex. A DOCX `Heading 1` titled "The Arrival" produces no chapter.

**Files:**
- Modify: `apps/api/src/echodraft_api/ingestion.py` — `_extract()` DOCX/EPUB branches emit `(text, warnings, signals)`; EPUB iterates in **spine order**; `process()` persists `chapter_signals.json` under `root/sources/{source_id}/structure_signals/` and adds `structureSignalsPath` to the source manifest payload (bump its schemaVersion)
- Modify: `libs/db/src/echodraft_db/models.py` — `SourceDocumentRecord.structure_signals_path: Mapped[str | None]`; migration + repair entry (next free number; `down_revision` = current head)
- Modify: `apps/api/src/echodraft_api/structure.py` — `extract()` loads signals for `container.sources.latest(project_id)` and passes to compiler; `_write_manifest` pipeline list += `"container_chapter_signals"`, quality gains `chaptersFromContainerSignals` count
- Modify: `apps/api/src/echodraft_api/structure_parsing.py` — `StructureCompiler.compile(text, max_chars, chapter_signals=None)`; signal-driven chapter promotion (see below)
- Modify docs: `docs/pipeline/structure/structure-parser-v2.md`, `docs/pipeline/ingestion/pdf-ocr-ingestion.md` sibling note or `clean-text-review.md` as fits, `docs/architecture/pipeline-manifest-spec.md` (manifest keys)
- Test: `apps/api/tests/test_ingestion.py` (signals emitted for heading-styled DOCX + multi-item EPUB), `apps/api/tests/test_structure.py` (signals → chapters end-to-end)

**Interfaces:**
- Produces: signal shape (list, JSON file):
  ```json
  {"title": "The Arrival", "sourceKind": "docx_heading" | "epub_toc" | "epub_spine", "level": 1, "anchorText": "The Arrival", "confidence": 0.95}
  ```
  `anchorText` = the heading's exact text (first 120 chars, stripped). **Resolution is by anchor-text matching against parsed blocks** (cleaning shifts offsets — never trust raw offsets): in `chapter_candidates()`, a block whose stripped text equals (case-insensitive, whitespace-collapsed) a signal's `anchorText` is promoted to a chapter boundary with `evidence["reason"] = signal.sourceKind`, bypassing `EXPLICIT_CHAPTER_RE`. Signals that match no block produce a parser warning (`code="container_signal_unmatched"`). Regex detection continues to run; dedupe by block (a block promoted by both keeps the container reason).
- DOCX extraction: paragraphs whose `paragraph.style.name` matches `Heading 1`/`Heading 2`/`Title` become signals (level from style; `Title` → level 0, confidence 0.9; Heading 1 → 0.95, Heading 2 → 0.75 — only levels ≤ 1 promote chapters, level 2 becomes a scene-break hint recorded in evidence but NOT a new chapter in this task).
- EPUB: spine-ordered documents; each `book.toc` entry (flatten nested sections) → signal `epub_toc` confidence 0.95 with anchorText = its title; additionally each spine item's first `<h1>` (parse with BeautifulSoup before flattening) → `epub_spine` confidence 0.8 if not already covered by a TOC signal with the same anchor.

**Steps:**

- [ ] **Step 1 (RED): end-to-end test.** In `test_structure.py`: build a DOCX via `document.add_heading("The Arrival", level=1)` + paragraphs + second heading "The Departure" (no "Chapter" keyword anywhere), import, run `structure/extract`, assert exactly 2 chapters titled "The Arrival"/"The Departure". Same-shaped EPUB test: 2 `EpubHtml` items with `<h1>`s, populated `book.toc`/`book.spine` (copy `test_ingestion.py::epub_bytes` and extend). Both fail on main.
- [ ] **Step 2: ingestion emits signals** (DOCX styles; EPUB spine order + TOC). Unit-test signals content in `test_ingestion.py` (assert JSON file exists at manifest's `structureSignalsPath`, holds expected titles/kinds/order).
- [ ] **Step 3: persistence** — model column + migration + repair + manifest key.
- [ ] **Step 4: compiler consumes signals** with anchor-text promotion + unmatched-signal warning + evidence reason.
- [ ] **Step 5 (GREEN):** step-1 tests pass; full suite (existing txt/markdown structure tests must be unaffected — signals default `None`).
- [ ] **Step 6: reparse coverage** — reparse mints a new source_id (main.py:551-581): extend `test_ingestion.py` reparse test to a DOCX source, assert fresh signals file for the new source id and that `structure/extract` after reparse still yields the container chapters.
- [ ] **Step 7: full battery, migration round-trip, docs, commit `feat(structure): DOCX heading and EPUB spine/TOC chapter signals`, merge, push, CI green.**

---

### Task A3 (G6): Corrections propagate and teach

**Branch:** `feat/g6-feedback-loop`

**Problem:** Every confirmation is a single-row write. Confirming a speaker on one line does nothing for the 40 other lines with the same speaker hint (`SpeakerAttributionService.update`, speaker_attribution.py:88-108). Merging characters doesn't re-point the source's attributions (only voice assignment transfers — `merge_characters`, repository.py:1025-1073). Rejected "possible duplicate" flags re-appear on every re-discovery. LLM prompts (`_merge_prompt` cast_discovery.py:568-593, `_llm_prompt` speaker_attribution.py:270-291) never see past human decisions.

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py` — propagation in `update()`; few-shot in `_llm_prompt`
- Modify: `libs/db/src/echodraft_db/repository.py` — `merge_characters` re-points `SpeakerAttributionRecord.character_id` source→target; new `SpeakerAttributionRepository` helper for same-name unresolved rows
- Create: `cast_merge_decisions` table — `CastMergeDecisionRecord(id, project_id, name_a, name_b (normalized, sorted pair), decision: "confirmed"|"rejected", reason, created_at)` + migration + repair + repository accessors
- Modify: `apps/api/src/echodraft_api/cast_discovery.py` — record `confirmed` decision on merge; before creating a `possible_duplicate` issue check for a `rejected` decision on that name pair and skip; `_merge_prompt` gains "Previously confirmed decisions" few-shot block from the decisions table
- Modify: `apps/api/src/echodraft_api/main.py` — `POST /api/v1/characters/{character_id}/reject-merge` (body: other character/candidate name + reason) recording a `rejected` decision and resolving the linked issue
- Modify: `apps/web` — Character Bible / StructureWarnings gain "Not a duplicate" affordance calling reject-merge (minimal; A4 does the full queue)
- Modify docs: `docs/pipeline/casting/character-bible.md`, `docs/pipeline/casting/speaker-attribution.md`
- Test: `apps/api/tests/test_speaker_attribution.py`, `apps/api/tests/test_character_bible.py`, `apps/api/tests/test_structure.py` (duplicate-issue suppression)

**Interfaces:**
- Produces:
  - `SpeakerAttributionService.update(...)` — when the update sets `character_id` with status approved/user action, propagate: all other attributions in the same project with the same normalized `speaker_name`, not `user_locked`, and (`character_id IS NULL` or status in {"pending","needs_review"}) get `character_id`, `status="approved"`, `confidence=max(existing, 0.9)`, `evidence["method"]="propagated_from_confirmation"` + `evidence["sourceAttributionId"]`. Response model gains `propagatedCount: int` (extend the endpoint's return — check current response shape first and stay backward compatible).
  - `merge_characters` also re-points attributions and records a `confirmed` `CastMergeDecision` for the name pair.
  - Cast discovery consults decisions: rejected pair → no new duplicate issue (evidence notes suppression); `_merge_prompt` includes up to 10 most recent decisions as `- "A" and "B": confirmed same person` / `…: different people` lines.
  - `_llm_prompt` includes up to 5 few-shot lines from approved+locked attributions of the same project: `Text: "<120 chars>" → Speaker: <name>`.
  - User-locked directions already persist and survive re-inference (`SegmentDirectionRepository.upsert` guard, repository.py:1370-1404) — G6's "directions as facts" is satisfied there; document it, don't rebuild it.
- Consumes: nothing from A1/A2.

**Steps:**

- [ ] **Step 1 (RED): propagation test** — build a chapter with 3+ dialogue lines from the same hinted speaker (dialogue-tag format per existing test corpus in `test_speaker_attribution.py`), force low-confidence/pending rows (or clear character links), PATCH one attribution to a character, assert the sibling rows are now approved+linked and response carries `propagatedCount >= 2`.
- [ ] **Step 2 (RED): merge re-points attributions** — attribute lines to character S, merge S into T, assert attributions now reference T and a confirmed decision row exists.
- [ ] **Step 3 (RED): rejection suppresses re-flagging** — trigger a `possible_duplicate` issue (fixtures exist: `test_possible_duplicate_cast_name_creates_review_issue`, test_structure.py:614), call reject-merge, re-run discovery, assert no new duplicate issue for that pair and old issue resolved.
- [ ] **Step 4: implement** (propagation helper + repository queries by normalized name; decisions table + migration + repair; discovery integration; endpoint).
- [ ] **Step 5: few-shot injection** — unit-level: monkeypatch the LLM provider (patterns in `test_structure.py:395+` / `test_local_llm.py`), capture the prompt, assert the decisions/exemplar lines appear.
- [ ] **Step 6 (GREEN), frontend affordance, web lint/typecheck, full battery, migration round-trip, docs, commit `feat(loop): confirmations propagate, merges teach, rejections stick`, merge, push, CI green.**

---

### Task A4 (G7): Evidence-rich one-click triage queues

**Branch:** `feat/g7-triage-queues`

**Problem:** `StructureWarnings.tsx` computes-and-prints each row's `reviewAction` token but offers no button; `evidenceGraph`/`possibleMatches`/`speakerRule`/`llmEvidence` are fetched and dropped; the only wired action is the evidence-blind generic "Mark resolved". `CastReview.tsx` shows only `evidence.textPreview`, unordered.

**Files:**
- Modify: `apps/api/src/echodraft_api/main.py` + a small service — `POST /api/v1/issues/{issue_id}/apply-action`: executes the issue's `metadata.reviewAction`: `merge_cast` → `casting.merge_characters(candidate → chosen match)` (body may carry `targetCharacterId` when multiple `possibleMatches`); `confirm_cast` → create the character from the candidate metadata (reuse `CastDiscoveryService._apply_candidate`'s shape) — then mark the issue resolved with `resolvedBy: "apply_action"`. Unknown/absent action → 422.
- Modify: `apps/web/app/components/structure/StructureWarnings.tsx` — action buttons per row (Apply / target-select for merges / "Not a duplicate" via A3's reject-merge / Dismiss), render evidence: possibleMatches, evidenceGraph counts (speakerEvidenceCount/mentionEvidenceCount/confidence), preview
- Modify: `apps/web/app/components/voices/CastReview.tsx` — order rows by confidence ascending (most doubtful first) with a count header ("N need review"), show `evidence.speakerRule`/method alongside preview; "apply to all same speaker" note appears when propagation (A3) resolves siblings — display `propagatedCount` feedback after save
- Modify: `apps/web/app/api.ts`, `apps/web/app/project-dashboard.tsx` — client calls + refresh wiring (re-fetch structure quality/issues after apply-action)
- Modify docs: `docs/pipeline/review/review-patch-workbench.md` or structure-parser doc section on review queues
- Test: `apps/api/tests/test_structure.py` or new `test_triage.py` (apply-action for both actions + 422 path)

**Interfaces:**
- Consumes: A3's reject-merge endpoint + propagation counts; existing issue metadata (`reviewAction`, `candidateName`, `possibleMatches`, `evidenceGraph`).
- Produces: `POST /api/v1/issues/{issue_id}/apply-action` (body `{targetCharacterId?: string}`) → `{issue: Issue, result: {action: str, characterId?: str}}`.

**Steps:**

- [ ] **Step 1 (RED):** API tests: `merge_cast` issue → apply-action with target → characters merged + issue resolved; `confirm_cast` issue → apply-action → character exists + issue resolved; issue without reviewAction → 422.
- [ ] **Step 2: implement backend** (thin service; reuse repository/service functions — no new business logic beyond dispatch).
- [ ] **Step 3 (GREEN) + full backend battery.**
- [ ] **Step 4: frontend queue wiring** (buttons, evidence rendering, ordering, refresh). `npm run web:lint`, `npm run web:typecheck`; if the Playwright smoke config covers these panels, run `npm run web:test:smoke` (chromium already installed in CI).
- [ ] **Step 5: docs, commit `feat(review): one-click evidence-backed triage queues`, merge, push, CI green.**

---

## Phase exit criteria (roadmap)
No UI control silently no-ops (G4 truthful capability + transmission); a single confirmation resolves its siblings and improves later auto-detection (A3); reviewers act on evidence-rich cards (A4); well-formed DOCX/EPUB structure correctly on import (A2).
