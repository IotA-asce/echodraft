# G7 Evidence Triage Queues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close roadmap G7 by turning cast review evidence issues into concrete one-click backend actions and frontend triage controls.

**Architecture:** Add a thin issue-action dispatcher that reads the existing `metadata.reviewAction` contract and reuses current casting repositories. Keep issue metadata as the source of truth, resolve handled issues append-only, and refresh the current review/readiness surfaces after each action.

**Tech Stack:** FastAPI, Pydantic v2 domain models, SQLAlchemy repositories, Next.js/TypeScript.

---

### Task 1: Backend Issue Action API

**Files:**
- Modify: `libs/domain-models/src/echodraft_domain/models.py`
- Modify: `apps/api/src/echodraft_api/main.py`
- Test: `apps/api/tests/test_structure.py`

**Steps:**
1. Add `IssueApplyActionRequest`, `IssueApplyActionResult`, and `IssueApplyActionResponse` domain models.
2. Write failing API tests for `merge_cast`, `confirm_cast`, and missing/unsupported `reviewAction`.
3. Implement `POST /api/v1/issues/{issue_id}/apply-action`.
4. Reuse `casting.merge_characters` for `merge_cast`.
5. Reuse `casting.create_character` for `confirm_cast`.
6. Mark handled issues resolved and return the updated issue plus action result.
7. Run the targeted backend tests.

### Task 2: Frontend Triage Controls

**Files:**
- Modify: `apps/web/app/api.ts`
- Modify: `apps/web/app/components/structure/StructureWarnings.tsx`
- Modify: `apps/web/app/components/voices/CastReview.tsx`
- Modify: `apps/web/app/project-dashboard.tsx`

**Steps:**
1. Add typed `applyIssueAction` and `rejectCharacterMerge` API helpers.
2. Add action props to `StructureWarnings` for apply, reject, and dismiss.
3. Render evidence details from `possibleMatches`, `evidenceGraph`, previews, and confidence.
4. Add target selection for merge issues and one-click confirm for low-confidence cast issues.
5. Order `CastReview` by lowest confidence first and surface propagation feedback from `propagatedCount`.
6. Refresh issues, structure quality, characters, and attributions after successful actions.
7. Run web lint and typecheck.

### Task 3: Docs And Verification

**Files:**
- Modify: `docs/pipeline/review/review-patch-workbench.md`
- Modify: `docs/pipeline/casting/character-bible.md`

**Steps:**
1. Document the `apply-action` issue contract and frontend behavior.
2. Run backend tests, ruff, mypy, web lint, and web typecheck.
3. Commit as `feat(review): add evidence-backed triage actions`.
4. Merge into `main` and push `main` plus the feature branch if validation passes.
