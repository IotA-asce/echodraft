# G14 Voice Facets And Auditions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make voice suggestions use structured Kokoro voice-ID facets and audition against representative character dialogue instead of generic sample text.

**Architecture:** Avoid a database migration by deriving voice facets from `backend` and `providerVoiceId` at API serialization/ranking time. Reuse speaker-attribution-to-segment joins to select a bounded representative line for each character.

**Tech Stack:** FastAPI service code, Pydantic domain models, SQLAlchemy repositories, pytest, ruff, mypy.

---

### Task 1: Add Voice Facet And Audition Tests

**Files:**
- Modify: `apps/api/tests/test_tts_production_upgrade.py`

**Step 1:** Add assertions that Kokoro voice IDs such as `af_heart` expose facets like `gender:feminine` and `locale:american`.

**Step 2:** Add a test where a character has an approved speaker attribution and voice suggestions return that segment text as `sampleText`.

### Task 2: Add Derived Facets To Domain Responses

**Files:**
- Modify: `libs/domain-models/src/echodraft_domain/models.py`
- Modify: `apps/api/src/echodraft_api/main.py`
- Modify: `apps/web/app/api.ts`

**Step 1:** Add `facets: list[str]` to `VoiceProfile` and `VoiceSuggestion`.

**Step 2:** Add a helper that parses Kokoro voice-ID prefixes: `af/am/bf/bm` into locale and gender facets, and recognizes useful lexical suffixes when present.

**Step 3:** Include facets in voice list/create/update responses and voice suggestions.

### Task 3: Rank Suggestions By Facets And Character Lines

**Files:**
- Modify: `apps/api/src/echodraft_api/main.py`
- Modify: `libs/db/src/echodraft_db/repository.py`

**Step 1:** Add a repository helper that returns approved segment texts for a character.

**Step 2:** Use the first bounded representative line as `sampleText`; fall back to the existing generic audition line.

**Step 3:** Rank suggestions using matched traits from derived facets plus existing metadata.

### Task 4: Update Docs And Tracker

**Files:**
- Modify: `docs/progress-tracker.md`
- Modify: `docs/pipeline/casting/character-bible.md`
- Modify: `docs/history/analysis/gap-analysis.md`
- Modify: `docs/history/analysis/product-vision-analysis.md`

**Step 1:** Mark G14 Kokoro facets and representative-line auditions complete if validation passes.

**Step 2:** Keep broader casting work open only if a future UI/audio lineup remains outside this backend slice.

### Task 5: Validate And Ship

**Commands:**
- `uv run pytest apps/api/tests/test_tts_production_upgrade.py apps/api/tests/test_character_bible.py`
- `uv run pytest`
- `uv run ruff check apps/api/src apps/api/tests libs/db/src libs/domain-models/src`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src`
- `npm --prefix apps/web run typecheck`
- `npm --prefix apps/web run lint`

**Git:**
- Commit: `feat: add voice facets and auditions`
- Merge branch into `main`
- Push `main` and `feat/g14-voice-facets-auditions`
