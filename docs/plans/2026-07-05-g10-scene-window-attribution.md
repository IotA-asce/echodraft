# G10 Scene Window Attribution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Send contiguous same-scene context to the local LLM speaker-attribution pass while only allowing the LLM to update unresolved target rows.

**Architecture:** Keep deterministic attribution unchanged. Build LLM batches from unresolved target segments, expand each batch into same-scene ordered context windows, mark `TARGET` versus `CONTEXT` lines in the prompt, and ignore LLM attributions for context-only segment IDs. Preserve local-first safety by keeping locked rows protected and deterministic review rows when the LLM fails.

**Tech Stack:** FastAPI service code, SQLAlchemy ORM records, pytest monkeypatch tests, ruff, mypy.

---

### Task 1: Add Prompt Context Test

**Files:**
- Modify: `apps/api/tests/test_speaker_attribution.py`

**Step 1: Write the failing test**

Add a test that imports a scene with a labeled line and an unresolved quoted line, monkeypatches `LocalLlmService.extract`, runs `POST /api/v1/projects/{projectId}/speaker-attributions/run` with `useLocalLlm=true`, and asserts the captured prompt contains:
- a `TARGET` marker for the unresolved quoted segment
- a `CONTEXT` marker for the surrounding labeled segment
- the labeled segment text
- instruction text telling the model to return only target segment attributions

**Step 2: Run the focused failing test**

Run:

```bash
uv run pytest apps/api/tests/test_speaker_attribution.py::test_llm_prompt_includes_same_scene_context_window -q
```

Expected before implementation: fail because the prompt only lists unresolved segments.

### Task 2: Implement Scene Windows

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`

**Step 1: Add a window data structure**

Add an internal frozen dataclass with:
- `segments: list[SegmentRecord]`
- `target_segment_ids: set[str]`

**Step 2: Build context windows**

Replace direct `_segment_batches(unresolved_segments)` use in `_apply_local_llm` with a helper that:
- groups unresolved targets by scene
- includes all same-scene segments for each affected scene in manuscript order
- caps by existing segment/character batch limits
- records which segment IDs are actual unresolved targets

**Step 3: Update prompt construction**

Change `_llm_prompt` to accept `target_segment_ids` and render each line as:

```text
- TARGET <segmentId>: text
- CONTEXT <segmentId>: text
```

Add instruction: return attributions only for `TARGET` segment IDs; context lines are evidence only.

**Step 4: Guard result application**

When applying LLM output, ignore any `segmentId` that is not in the current window's `target_segment_ids`.

### Task 3: Preserve Evidence

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`

**Step 1: Add evidence fields**

When an LLM result is applied, include:
- `sceneWindowSegmentIds`
- `targetSegmentIds`

This gives review/debug context without changing the public schema.

### Task 4: Update Docs And Tracker

**Files:**
- Modify: `docs/pipeline/casting/speaker-attribution.md`
- Modify: `docs/progress-tracker.md`
- Modify: `docs/analysis/gap-analysis.md`
- Modify: `docs/analysis/product-vision-analysis.md`

**Step 1: Mark the G10 subitem**

Mark `Send contiguous scene windows to the LLM attribution pass` complete only after validation passes.

**Step 2: Keep G10 parent open**

Leave `Expand into full scene active-speaker and interruption model` unchecked.

### Task 5: Validate And Ship

**Commands:**
- `uv run pytest apps/api/tests/test_speaker_attribution.py`
- `uv run pytest`
- `uv run ruff check apps/api/src apps/api/tests libs/db/src libs/domain-models/src`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src`

**Git:**
- Commit: `feat: add scene windows to speaker attribution`
- Merge into `main`
- Push `main` and `feat/g10-scene-window-attribution`
