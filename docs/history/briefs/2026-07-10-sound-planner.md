# Deterministic Sound Planner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic, chapter-scoped sound planner that resolves Tier-0 assets and materializes auditable, idempotent automatic cues without changing manual sound-design behavior.

**Architecture:** Keep planning pure in a new `sound_planner.py` module: ordered scene/profile/segment inputs become planned placements and skip diagnostics with no database or filesystem access. A service layer loads project data, resolves Tier-0 assets, reconciles only unlocked `auto_generated` rows, and writes an append-only versioned sound-plan manifest plus the latest manifest pointer.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest, Ruff, strict mypy.

---

### Task 1: Lock the persistence and API contract with failing tests

**Files:**
- Create: `apps/api/tests/test_sound_planner.py`
- Modify: `apps/api/tests/test_migrations.py`
- Modify: `libs/domain-models/src/echodraft_domain/models.py`

**Step 1: Write pure planner tests**

Cover `speech_only` empty output, one ambience bed for a contiguous matching signature, confidence gating, sparse SFX budgeting, `noSfxRecommended`, per-segment `DirectionProfile.noSfx`, and deterministic evidence anchors.

**Step 2: Write API integration tests**

Create a structured project with stored atmosphere profiles, call `POST /api/v1/projects/{projectId}/chapters/{chapterId}/sound-plan`, and assert generated Tier-0 asset provenance, automatic cue evidence, manifest creation, and stable IDs/counts on an unchanged rerun.

**Step 3: Write locked/manual preservation tests**

Assert the planner leaves manual cues unchanged and never updates an existing `userLocked` automatic cue when its plan changes.

**Step 4: Write migration/repair tests**

Assert Alembic head and legacy SQLite repair add the asset provenance fields, cue provenance/control fields, and `auto_sound_design_json`.

**Step 5: Run focused tests and confirm failure**

Run: `uv run pytest apps/api/tests/test_sound_planner.py apps/api/tests/test_migrations.py -q`

Expected: FAIL because the sound planner, route, and additive columns do not exist yet.

### Task 2: Add additive database and domain fields

**Files:**
- Create: `libs/db/alembic/versions/0037_sound_planner.py`
- Modify: `libs/db/src/echodraft_db/models.py`
- Modify: `libs/db/src/echodraft_db/database.py`
- Modify: `libs/db/src/echodraft_db/ambience.py`
- Modify: `libs/domain-models/src/echodraft_domain/models.py`

**Step 1: Add generated-asset provenance**

Add nullable `model`, `prompt`, `seed`, indexed `cache_key`, and non-null `qa_status = "n/a"` to `ambience_assets`.

**Step 2: Add automatic-cue provenance and controls**

Add non-null `origin = "user_created"`, `evidence_json = "{}"`, `muted = false`, and `user_locked = false` to `ambience_cues`.

**Step 3: Add project sound settings storage**

Add nullable `auto_sound_design_json` to `project_production_settings` and expose it through production settings without changing current clients.

**Step 4: Extend repositories and API models compatibly**

Accept the new fields as keyword-only optional arguments while retaining all existing manual endpoint defaults and response fields.

**Step 5: Run migration tests**

Run: `uv run pytest apps/api/tests/test_migrations.py -q`

Expected: PASS with no Alembic/model drift.

### Task 3: Implement the pure deterministic planner

**Files:**
- Create: `apps/api/src/echodraft_api/sound_planner.py`
- Test: `apps/api/tests/test_sound_planner.py`

**Step 1: Define immutable planner inputs and outputs**

Represent scenes, segments, atmosphere profiles, settings, planned cues, anchors, and skip diagnostics with frozen dataclasses.

**Step 2: Implement restraint-first ambience planning**

Return no placements for `speech_only`; require scene confidence at least `0.65`; emit one ambience placement at the first scene of each contiguous bed-signature run and reuse its asset choice through the run.

**Step 3: Implement sparse SFX selection**

Require event confidence at least `0.80`; enforce default chapter budgets of two for `light_cinematic` and five for `dramatized`; skip scene/segment no-SFX flags before spending budget; anchor by exact normalized substring then Jaccard fallback.

**Step 4: Keep unsupported Tier-0 music explicit**

Record opening/peak music decisions as skipped with `tier0_music_unavailable` rather than inventing a music asset.

**Step 5: Run pure tests**

Run: `uv run pytest apps/api/tests/test_sound_planner.py -q`

Expected: planner unit tests PASS; integration tests proceed to the service layer.

### Task 4: Materialize plans safely and write manifests

**Files:**
- Modify: `apps/api/src/echodraft_api/sound_planner.py`
- Modify: `apps/api/src/echodraft_api/main.py`
- Test: `apps/api/tests/test_sound_planner.py`

**Step 1: Load chapter inputs and fill missing profiles**

Validate project/chapter ownership, run the non-blocking atmosphere pass only when a scene profile is absent, then reload ordered scenes, segments, direction flags, and settings.

**Step 2: Resolve content-addressed Tier-0 assets**

Resolve ambience/SFX tags through `TierZeroSoundBank`; reuse project asset rows by `cache_key`; persist bank model, prompt/query, cache key, QA status, and CC0 license note.

**Step 3: Reconcile only automatic unlocked cues**

Use a deterministic `planKey` in `evidence_json`. Reuse unchanged rows, update changed unlocked automatic rows, remove no-longer-planned unlocked automatic rows, and leave all manual or `user_locked` rows byte-for-byte untouched.

**Step 4: Write append-only and latest manifests**

Write `sound_plan_manifest.<id>.json` first and then `sound_plan_manifest.json`, including profiles, planned cues, budgets, skipped decisions, materialized IDs, and diagnostics.

**Step 5: Add the synchronous chapter route**

Add `POST /api/v1/projects/{projectId}/chapters/{chapterId}/sound-plan` with a typed request/result contract and 201 response.

**Step 6: Run focused tests**

Run: `uv run pytest apps/api/tests/test_sound_planner.py apps/api/tests/test_sound_design.py apps/api/tests/test_tier0_sound.py apps/api/tests/test_atmosphere_profiles.py -q`

Expected: PASS; existing manual upload/cue/mix paths remain green.

### Task 5: Document, verify, and deliver

**Files:**
- Modify: `docs/plans/v2-implementation-roadmap.md`
- Modify: `docs/progress-tracker.md`

**Step 1: Record implementation evidence**

Mark W6.3 complete only after all validation passes and note deterministic planning, Tier-0 resolution, idempotency, and locked/manual preservation.

**Step 2: Run full verification**

Run:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src --strict`

Expected: all commands PASS.

**Step 3: Commit the feature**

Run: `git add <W6.3 files> && git commit -m "feat: add deterministic sound planning"`

**Step 4: Merge and push**

Switch to `main`, merge `feat/sound-planner` with a merge commit, push `main`, and push the feature branch for traceability.
