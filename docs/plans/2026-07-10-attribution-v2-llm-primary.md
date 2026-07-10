# Attribution v2 LLM-Primary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make scene-window LLM attribution the primary non-trivial speaker resolver while preserving deterministic short-circuits, user locks, sibling propagation, and one row per segment.

**Architecture:** Keep the current deterministic cascade as a pre-pass and v1 as the default. Behind `ECHODRAFT_ATTRIBUTION_V2_ENABLED`, target every non-trivial unlocked row, run scene windows in parallel with roster/candidate/conversation-state evidence, vote on low-confidence rows, then perform deterministic book-level alternation and seam repair before writing an additive manifest.

**Tech Stack:** Python 3.12, FastAPI service layer, Ollama structured extraction, SQLAlchemy repositories, pytest, Ruff, mypy.

---

### Task 1: Voting and conversation-state primitives

**Files:**
- Create: `apps/api/src/echodraft_api/attribution_v2.py`
- Create: `apps/api/tests/test_attribution_v2.py`

**Steps:**
1. Write failing tests for majority voting, agreement-derived confidence, deterministic tie handling, conversation state, and two-speaker alternation repair.
2. Run `uv run pytest apps/api/tests/test_attribution_v2.py -q` and confirm import/test failures.
3. Implement pure typed primitives with no persistence or network calls.
4. Re-run the focused tests and expect all to pass.

### Task 2: Feature-flagged LLM-primary MAP and vote pass

**Files:**
- Modify: `apps/api/src/echodraft_api/config.py`
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`
- Modify: `apps/api/tests/test_attribution_v2.py`

**Steps:**
1. Write failing integration tests asserting deterministic explicit/narrator short-circuits, all other unlocked rows as TARGETs, parallel MAP prompts with candidate evidence and incoming conversation state, three-sample voting for low results, and locked-row preservation.
2. Add `attribution_v2_enabled`; route only the flagged path to the new implementation.
3. Parse only TARGET IDs, resolve only Character Bible identities or narrator/unknown, and fall back to pre-pass rows when the model fails.
4. Run `uv run pytest apps/api/tests/test_attribution_v2.py apps/api/tests/test_speaker_attribution.py -q`.

### Task 3: REDUCE, manifest, and evaluation gate

**Files:**
- Modify: `apps/api/src/echodraft_api/speaker_attribution.py`
- Modify: `apps/api/scripts/run_eval.py`
- Modify: `docs/plans/2026-07-07-v2-implementation-roadmap.md`
- Modify: `docs/progress-tracker.md`
- Create: `docs/analysis/eval-baselines/2026-07-10-attribution-v2-gate.md`

**Steps:**
1. Write failing tests for cross-window state stitching, safe A/B/A repair, one row per segment, additive `attribution_manifest.json`, and user-lock survival.
2. Implement the bounded reduce and manifest; add `--attribution-v2` to the eval harness.
3. Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy apps/api/src libs/domain-models/src libs/db/src`.
4. Run the comparison harness to a temporary output; require attribution accuracy at least 0.98 and no baseline regression.
5. Record the gate, mark W3.5 complete, commit, merge to `main`, and push both branches without staging `.env` or unrelated `package-lock.json` changes.
