# G19 Persistent Local TTS Worker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep managed Kokoro ONNX resident across local previews and segment renders.

**Architecture:** Add a process-level worker manager owned by the API container. Managed Kokoro uses a newline-delimited JSON helper mode when the worker manager is injected; setup validation and all non-managed providers keep their existing one-shot subprocess behavior.

**Tech Stack:** FastAPI, Pydantic domain models, subprocess-managed local Python helper, pytest.

---

### Task 1: Add Resident Worker

**Files:**
- Create: `apps/api/src/echodraft_api/tts_worker.py`
- Modify: `apps/api/src/echodraft_api/tts_providers.py`
- Modify: `apps/api/src/echodraft_api/kokoro_setup.py`

**Steps:**
1. Add a `TtsWorkerManager` that lazily starts one managed Kokoro subprocess for the active runtime paths.
2. Add `--serve-json` to the generated managed Kokoro helper while preserving one-shot `--list-voices` and render behavior.
3. Inject the worker manager into `ManagedKokoroOnnxAdapter`; use resident mode when present, subprocess mode otherwise.

### Task 2: Add Lifecycle And Status

**Files:**
- Modify: `apps/api/src/echodraft_api/container.py`
- Modify: `apps/api/src/echodraft_api/main.py`
- Modify: `libs/domain-models/src/echodraft_domain/models.py`
- Modify: `apps/web/app/api.ts`

**Steps:**
1. Store the worker manager in `AppContainer`.
2. Stop workers on provider/settings changes and FastAPI shutdown.
3. Add `GET /api/v1/settings/tts/worker` with provider, setup mode, worker mode, state, pid, request count, and last error.

### Task 3: Verify Behavior

**Files:**
- Create: `apps/api/tests/test_tts_worker.py`
- Modify: `apps/api/tests/test_kokoro_setup.py`

**Steps:**
1. Test resident worker process reuse and WAV output with a fake JSON worker.
2. Test adapter resident and subprocess provenance.
3. Test the worker status endpoint and settings-change cleanup.
4. Run the G19 validation command set from the tracker.

### Task 4: Document And Ship

**Files:**
- Modify: `docs/pipeline/tts/tts-production-upgrade.md`
- Modify: `docs/analysis/gap-analysis.md`
- Modify: `docs/analysis/product-vision-analysis.md`
- Modify: `docs/progress-tracker.md`

**Steps:**
1. Document resident managed Kokoro behavior and the status endpoint.
2. Mark G19 complete only after validation.
3. Commit, merge to `main`, and push `main` plus `feat/g19-persistent-tts-worker`.
