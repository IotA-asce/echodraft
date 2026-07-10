# Phase 3 Cast Depth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Start Phase 3 by improving cast discovery, speaker attribution, and voice assignment quality for gaps G9, G10, and G14.

**Architecture:** Reuse the existing `characters.traits_json`, `characters.aliases_json`, speaker attribution evidence, and voice profile APIs. Avoid schema changes in this slice; add deterministic enrichment and review evidence that later LLM/local-worker features can build on.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic domain models, pytest, existing local-first repositories.

---

### Task 1: Character Alias And Trait Extraction

**Files:**
- Modify: `apps/api/src/echodraft_api/cast_discovery.py`
- Test: `apps/api/tests/test_structure.py`

**Step 1: Write tests**

Add coverage that a manuscript with names such as `Captain Mara`, `Mara`, and `the young Irish captain` produces one active character with alias and trait evidence instead of duplicate records.

**Step 2: Implement deterministic enrichment**

Add a small local nickname/honorific normalizer and trait extractor:
- Strip common honorifics/titles into aliases.
- Add alias candidates from nearby mentions.
- Extract conservative traits for age, accent/nationality, role/title, and gendered pronouns only when directly observed.
- Store traits in `traits_json` and evidence in the existing notes/evidence graph.

**Step 3: Verify**

Run targeted structure/cast tests.

### Task 2: Speaker Alternation And Pronoun Evidence

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`
- Test: `apps/api/tests/test_speaker_attribution.py`

**Step 1: Write tests**

Add coverage for adjacent dialogue where an unlabeled quote follows a labeled quote and narration says `she said` or `he replied`.

**Step 2: Implement deterministic evidence**

Add bounded heuristics that:
- Use nearby approved/labeled speakers for alternation hints.
- Capture pronoun evidence in attribution metadata.
- Propose a new speaker name when a high-confidence speaker label is present but no Character Bible row exists.

**Step 3: Verify**

Run targeted speaker attribution tests.

### Task 3: Trait-Ranked Voice Suggestions

**Files:**
- Modify: `libs/domain-models/src/echodraft_domain/models.py`
- Modify: `apps/api/src/echodraft_api/main.py`
- Modify: `apps/web/app/api.ts`
- Test: `apps/api/tests/test_tts_production_upgrade.py` or `apps/api/tests/test_structure.py`

**Step 1: Write tests**

Add API coverage for a character with traits and a set of voice profiles whose provider IDs or style prompts imply gender/accent/age. Assert ranked suggestions favor matching voices and include explanation evidence.

**Step 2: Implement API**

Add a read-only endpoint such as `GET /api/v1/characters/{character_id}/voice-suggestions` that ranks existing project voices by trait overlap and returns explanation metadata.

**Step 3: Verify**

Run targeted API tests plus typecheck/lint.

### Task 4: Tracker And Docs

**Files:**
- Modify: `docs/progress-tracker.md`
- Modify: `docs/pipeline/casting/character-bible.md`
- Modify: `docs/pipeline/casting/speaker-attribution.md`

**Step 1: Update docs**

Mark completed subitems under G9/G10/G14 only. Keep parent Phase 3 open until every roadmap bullet is finished.

**Step 2: Verify**

Run `git diff --check` and the relevant backend validation commands.
