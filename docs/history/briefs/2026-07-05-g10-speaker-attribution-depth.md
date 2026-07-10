# G10 Speaker Attribution Depth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a focused deterministic speaker-attribution depth slice for two-speaker alternation, broader speech-action pronoun cues, and cast proposals from confident unmatched speaker labels.

**Architecture:** Keep speaker attribution local-first and conservative. Extend `SpeakerAttributionService` so deterministic generation can use a scene-ordered window around each dialogue segment, link high-confidence unknown labels into Character Bible records, and preserve review status for inferred rows.

**Tech Stack:** FastAPI service code, SQLAlchemy-backed repositories, pytest, ruff, mypy.

---

### Task 1: Add Alternation And Coreference Tests

**Files:**
- Modify: `apps/api/tests/test_speaker_attribution.py`

**Step 1:** Add a failing test for a two-speaker exchange where the middle unlabeled quote is assigned to the opposite speaker via alternation evidence.

**Step 2:** Add a failing test for broader action-beat pronoun cues such as `"Go," Mara whispered.` and `he muttered`.

**Step 3:** Add a failing test that a confident speaker label with no existing character creates a Character Bible record and links the attribution.

### Task 2: Implement Deterministic Speaker Context

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`

**Step 1:** Pass a wider ordered segment window into deterministic attribution.

**Step 2:** Implement a conservative `_turn_context_hint` that handles two labeled neighbors and same-scene alternation.

**Step 3:** Expand `_pronoun_cue` to detect speech verbs before or after quoted text.

### Task 3: Propose Missing Cast From Speaker Attribution

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`

**Step 1:** If a labeled dialogue segment has high parser confidence and no character match, create a supporting Character Bible record from the speaker label.

**Step 2:** Add the new record to the in-memory character index so later rows in the same run can link to it.

**Step 3:** Record evidence in the attribution row as `proposed_cast_from_speaker_attribution`.

### Task 4: Update Docs And Tracker

**Files:**
- Modify: `docs/progress-tracker.md`
- Modify: `docs/pipeline/casting/speaker-attribution.md`
- Modify: `docs/history/analysis/gap-analysis.md`
- Modify: `docs/history/analysis/product-vision-analysis.md`

**Step 1:** Mark G10 subitems for turn-taking, broader pronoun/coreference, and cast proposal as complete only after tests pass.

**Step 2:** Keep G10 parent open if scene-level transcript/review UX or full scene active-speaker sets remain incomplete.

### Task 5: Validate And Ship

**Commands:**
- `uv run pytest apps/api/tests/test_speaker_attribution.py`
- `uv run pytest`
- `uv run ruff check apps/api/src apps/api/tests libs/db/src libs/domain-models/src`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src`

**Git:**
- Commit: `feat: deepen speaker attribution`
- Merge branch into `main`
- Push `main` and `feat/g10-speaker-attribution-depth`
