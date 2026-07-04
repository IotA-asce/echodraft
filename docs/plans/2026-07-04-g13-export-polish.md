# G13 Export Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship M4B export, tagged MP3 export, optional retail samples, and an export QA scorecard while keeping artifacts local and manifest-driven.

**Architecture:** Continue the existing `ExportService` package flow: build a preflight plan, stage selected chapter outputs, write `export_manifest.json`, zip all referenced artifacts, and persist only package paths/status in SQLite. FFmpeg-dependent paths must fail closed through estimate blockers when FFmpeg is unavailable; non-FFmpeg QA falls back to local WAV analysis.

**Tech Stack:** FastAPI/Python 3.12, stdlib `wave`/`zipfile`/`subprocess`, existing `audio_analysis` and `mastering` helpers, Next.js/React/TypeScript dashboard.

---

### Task 1: Branch Integration

**Files:**
- Modify: existing G13 worktree on `feat/g13-export-polish`

**Step 1: Update branch to target**

Run: `git merge main`

Expected: branch includes the latest G7 merge before export changes are committed.

**Step 2: Reapply worker patch**

Run: `git stash pop`

Expected: worker changes apply cleanly or expose conflicts to resolve.

### Task 2: Backend Export Contract

**Files:**
- Modify: `apps/api/src/echodraft_api/exporting.py`
- Modify: `libs/domain-models/src/echodraft_domain/models.py`
- Test: `apps/api/tests/test_production_workbench.py`

**Step 1: Verify tests cover G13**

Run: `uv run pytest apps/api/tests/test_production_workbench.py -q`

Expected: M4B estimate/export, MP3 metadata, retail sample, and QA manifest tests pass.

**Step 2: Fix backend issues**

Implement only gaps exposed by tests, Ruff, mypy, or subagent audit. Preserve existing export blockers for missing FFmpeg, missing cover, missing renders, rights failures, and blocking issues.

**Step 3: Validate backend**

Run:

```bash
uv run pytest apps/api/tests/test_production_workbench.py apps/api/tests/test_mastering.py -q
uv run ruff check apps/api/src/echodraft_api/exporting.py apps/api/tests/test_production_workbench.py libs/domain-models/src/echodraft_domain/models.py
uv run mypy apps/api/src/echodraft_api/exporting.py libs/domain-models/src/echodraft_domain/models.py
```

Expected: all pass.

### Task 3: Frontend Export Controls

**Files:**
- Modify: `apps/web/app/api.ts`
- Modify: `apps/web/app/components/export/ExportPanel.tsx`
- Modify: `apps/web/app/project-dashboard.tsx`
- Modify: `apps/web/app/globals.css`

**Step 1: Validate web typing**

Run:

```bash
npm run web:lint
npm run web:typecheck
```

Expected: no lint or TypeScript errors.

**Step 2: Fix UI issues**

Ensure M4B can be requested, retail sample is configurable for MP3/M4B, and export history exposes QA pass/fail output rows without breaking existing WAV/MP3 flows.

### Task 4: Docs and Final Verification

**Files:**
- Modify: `docs/pipeline/export/export-polish.md`
- Modify: `docs/architecture/pipeline-manifest-spec.md`

**Step 1: Update docs**

Document implemented M4B, tagged MP3, retail sample, and manifest QA scorecard behavior.

**Step 2: Run full checks**

Run:

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
npm run web:lint
npm run web:typecheck
npm run web:test:smoke
```

Expected: all pass or any environment-only blocker is explicitly reported.

### Task 5: Ship

**Files:**
- All staged G13 changes only

**Step 1: Commit**

Run:

```bash
git add <G13 files>
git commit -m "feat(export): add M4B export polish"
```

**Step 2: Merge and push**

Run:

```bash
git switch main
git merge --no-ff feat/g13-export-polish
git push origin main feat/g13-export-polish
```

Expected: target branch and feature branch are both pushed.
