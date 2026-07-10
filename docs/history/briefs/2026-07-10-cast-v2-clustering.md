# Cast v2 Clustering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace pairwise cast-candidate adjudication with a feature-flagged, embedding-aware constrained clustering pipeline that emits auditable character profiles for automatic casting.

**Architecture:** Keep the existing mention extraction, durable mention ledger, character records, merge/split history, and v1 discovery path intact. Add a pure cast-v2 clustering module, select it behind `ECHODRAFT_CAST_V2_ENABLED`, reconcile once per resulting cluster, synthesize profile fields from pooled evidence, and extend the existing casting manifest without breaking current readers.

**Tech Stack:** Python 3.12, FastAPI service layer, Pydantic domain models, Ollama embeddings/structured extraction, SQLAlchemy repositories, pytest, Ruff, mypy.

---

### Task 1: Constrained alias clustering

**Files:**
- Create: `apps/api/src/echodraft_api/cast_v2.py`
- Test: `apps/api/tests/test_cast_v2.py`

**Step 1: Write failing unit tests**

Cover exact/honorific/embedding similarity, transitive agglomeration, same-window distinct-speaker cannot-link constraints, deterministic output ordering, and string-only fallback when embeddings are unavailable.

**Step 2: Run the focused tests and confirm failure**

Run: `uv run pytest apps/api/tests/test_cast_v2.py -q`

Expected: fail because `echodraft_api.cast_v2` does not exist.

**Step 3: Implement the pure clustering module**

Add surface-form aggregation, stdlib cosine similarity, weighted string/embedding scores, constrained agglomerative clustering, prior-ruling hooks, and manifest-ready cluster diagnostics. Keep clustering independent of persistence and network calls.

**Step 4: Run the focused tests**

Run: `uv run pytest apps/api/tests/test_cast_v2.py -q`

Expected: pass.

### Task 2: Feature-flagged service integration

**Files:**
- Modify: `apps/api/src/echodraft_api/config.py`
- Modify: `apps/api/src/echodraft_api/cast_discovery.py`
- Modify: `apps/api/tests/test_cast_v2.py`

**Step 1: Write failing integration tests**

Assert that v1 remains the default, the v2 flag batches distinct surface forms through the embedding service, clusters aliases before decisions, respects rejected merge rulings, and never mutates user-locked characters.

**Step 2: Run the focused tests and confirm failure**

Run: `uv run pytest apps/api/tests/test_cast_v2.py -q`

Expected: fail on the missing feature flag and service integration.

**Step 3: Implement the integration**

Add `cast_v2_enabled`, embed distinct surface forms in one request when the model is installed, fall back conservatively to string features with diagnostics, build one candidate per cluster, and use the existing durable decision/application gates once per cluster.

**Step 4: Run focused and regression tests**

Run: `uv run pytest apps/api/tests/test_cast_v2.py apps/api/tests/test_structure.py apps/api/tests/test_speaker_attribution.py -q`

Expected: pass.

### Task 3: Character profiles and manifest compatibility

**Files:**
- Modify: `apps/api/src/echodraft_api/cast_discovery.py`
- Modify: `apps/api/tests/test_cast_v2.py`

**Step 1: Write failing profile/manifest tests**

Assert one profile synthesis call per accepted cluster, profile persistence through existing role/traits/relationships/speaking-style columns, and a versioned casting manifest with `profiles` and `clusters` while retaining existing payload fields.

**Step 2: Run the focused tests and confirm failure**

Run: `uv run pytest apps/api/tests/test_cast_v2.py -q`

Expected: fail because v2 profiles and diagnostics are absent.

**Step 3: Implement profile synthesis and manifest output**

Add a strict structured-output schema, conservative deterministic fallback, pooled-evidence prompt, character-id resolution after applying each cluster, and additive manifest fields.

**Step 4: Run focused tests**

Run: `uv run pytest apps/api/tests/test_cast_v2.py -q`

Expected: pass.

### Task 4: Verification and roadmap completion

**Files:**
- Modify: `docs/plans/v2-implementation-roadmap.md`
- Modify: `docs/progress-tracker.md`

**Step 1: Run backend validation**

Run: `uv run pytest`

Run: `uv run ruff check .`

Run: `uv run mypy apps/api/src libs/domain-models/src libs/db/src`

Expected: all pass.

**Step 2: Run the available evaluation gate**

Run: `uv run python apps/api/scripts/run_eval.py --help` and run the replay/local corpus mode supported by available fixtures.

Expected: the harness is callable; record any unavailable private-corpus or local-model limitation explicitly.

**Step 3: Update trackers**

Mark W3.4 complete only after verification, preserving W3 as incomplete until W3.5-W3.7 ship.

**Step 4: Commit, merge, and push**

Commit on `feat/cast-v2-clustering`, merge with `--no-ff` into `main`, and push both updated `main` and the feature branch without staging `.env`, `test-assets/`, or unrelated lockfile changes.
