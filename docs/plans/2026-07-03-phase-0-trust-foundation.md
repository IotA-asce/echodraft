# Phase 0 — Trust Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "ready / resolved / fixed" live facts and make the pipeline reliably deliver what it computed — closing gaps G1, G2, G3, G12 from [`docs/analysis/gap-analysis.md`](../analysis/gap-analysis.md) per [`docs/product/roadmap.md`](../product/roadmap.md) Phase 0.

**Architecture:** Four independent, sequential tasks, each on its own feature branch merged `--no-ff` into `main` and pushed. Task 1 adds time-ordered render/export selection + a revision assertion at assembly. Task 2 makes patch force a fresh, correctly-voiced/directed re-render (server-side resolution). Task 3 replaces the readiness resolve-trap with re-derived, auto-resolving, re-surfacing semantics. Task 4 hardens SQLite (WAL/FK/busy_timeout, per-segment render serialization, uniqueness backstop), bounds the job executor, and adds CI with a schema-drift check.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic (SQLite), Pydantic v2, pytest; Next.js/TypeScript frontend; uv workspace; GitHub Actions.

## Global Constraints

Copied from `AGENTS.md` / `CLAUDE.md` / repo conventions — every task's requirements include these:

- **Never commit directly to `main`.** Each task: create feature branch from `main` → implement → verify → commit → merge `--no-ff` into `main` → push `origin main` and the feature branch.
- Segment stays the atomic editable/renderable unit.
- **Render and chapter render history stays append-only** — never delete render rows (status changes like `superseded` are allowed; deletion is not).
- Never store audio blobs in the DB — metadata and paths only.
- Local-first: no cloud-only assumptions.
- Update `docs/` when behavior changes (each task lists its doc touch-points).
- Backend verification (run from repo root, all must pass): `uv run pytest`, `uv run ruff check .`, `uv run mypy apps/api/src libs/domain-models/src libs/db/src` (mypy is `strict = true`).
- Frontend verification when `apps/web` is touched: `npm run web:lint`, `npm run web:typecheck`.
- Migration verification when persistence changes: `ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db uv run alembic -c libs/db/alembic.ini upgrade head` (create `.tmp/` first; delete the db file between runs).
- Alembic migrations live in `libs/db/alembic/versions/`, named `NNNN_short_name.py` with `revision = "NNNN_short_name"` (deterministic string ids, zero-padded sequence). Current head: `0022_readiness_reports`.
- **Every column added to a model must also get an idempotent repair entry** in `Database._repair_sqlite_schema_drift()` (`libs/db/src/echodraft_db/database.py:33-163`) — legacy local DBs are created by `create_all`, not Alembic.
- Ruff `line-length = 100`, `target-version = py312`. Tests live in `apps/api/tests/` (pytest `testpaths` is fixed to that).
- Tests use the fixtures in `apps/api/tests/conftest.py` (`settings`/`app`/`client` — fresh tmp SQLite per test, real container, `tts_provider = "mock"`). Follow the `wait_for_job` polling helper pattern used across test files.

---

### Task 1 (G1): Time-ordered render/export selection + assembly revision assertion

**Branch:** `feat/g1-render-ordering`

**Problem:** `segment_renders`, `chapter_renders`, `export_packages` have no `created_at`; every "latest" lookup orders by the random-uuid string PK descending, so a *newer* render can sort *older*. A patched segment's fresh render can silently miss the exported chapter. Assembly also never checks that the render it stitches matches the segment's current `revision`.

**Files:**
- Modify: `libs/db/src/echodraft_db/models.py` — `SegmentRenderRecord` (306-317), `ChapterRenderRecord` (337-347), `ExportPackageRecord` (438-446)
- Create: `libs/db/alembic/versions/0023_render_created_at.py`
- Modify: `libs/db/src/echodraft_db/database.py` — `_repair_sqlite_schema_drift`
- Modify: `libs/domain-models/src/echodraft_domain/models.py` — `SegmentRender` (~689), `ChapterRender` (~724), `ExportPackage` (~917)
- Modify: `apps/api/src/echodraft_api/rendering.py:44-56` (cache lookup), `:140-158` (history), `:186-204` (`_latest_successful`/`_tip`), `:100-109` + `:206-217` (`_model` — emit createdAt)
- Modify: `apps/api/src/echodraft_api/review.py:84-91` (previous-render lookup)
- Modify: `apps/api/src/echodraft_api/assembly.py:176-194` (active/history), `:196-230` (`_resolve_inputs` — ordering + revision assertion)
- Modify: `apps/api/src/echodraft_api/exporting.py:214-223` (`list_packages`), `:444-456` (`_active_render`)
- Modify: `apps/api/src/echodraft_api/readiness.py:487-494` (chapter-audio check lookup)
- Modify docs: `docs/architecture/current-pipeline-behavior.md` (render selection paragraph), `docs/domain/db-schema.md` (new columns)
- Test: `apps/api/tests/test_assembly.py` (add 2 tests), `apps/api/tests/test_review.py` (extend patch test assertion)

**Interfaces:**
- Produces: `created_at: Mapped[datetime | None]` on the three records (timezone-aware, app-side default `datetime.now(UTC)`); canonical ordering expression `ORDER BY created_at DESC, id DESC` for all "latest" lookups (SQLite sorts NULL last in DESC, so legacy rows sort oldest — correct); `ChapterAssembler._resolve_inputs` raises `ValueError` naming the segment when the selected render's `request_json["revision"] != segment.revision`; Pydantic models gain optional `createdAt`.
- Consumes: nothing from other tasks.

**Steps:**

- [ ] **Step 1: Write the failing selection test** in `apps/api/tests/test_assembly.py`. Build a project → import → extract → produce (copy the setup of `test_chapter_assembly_pins_ordered_renders_and_emits_stem`). Then render one segment a second time via `POST .../segments/{id}/generate` with `force: true` (payload shape from `test_review.py::render_payload`). Now make the ordering adversarial with a raw DB update: connect `sqlite3` to the test DB (path known from the `settings` fixture) and `UPDATE segment_renders SET id='rend_ffffffffffffffff' WHERE id=<old render id>` (also update the newer render's `parent_render_id` to match). Re-assemble (produce again with `force: false` is simplest — cache returns existing segment renders, then assembly runs), fetch `.../active-render` + its manifest, and assert the manifest embeds the **newer** render id, not `rend_ffffffffffffffff`. This fails on `main` because selection is `id DESC`.
- [ ] **Step 2: Run it, verify it fails** — `uv run pytest apps/api/tests/test_assembly.py -k adversarial -x`. Expected: assertion failure showing the old id was stitched.
- [ ] **Step 3: Add `created_at` columns.** In `models.py` add to each of the three records (copy the exact style of `PatchAttemptRecord.created_at` at models.py:435):
  ```python
  created_at: Mapped[datetime | None] = mapped_column(
      DateTime(timezone=True), nullable=True, default=lambda: datetime.now(UTC)
  )
  ```
  Migration `0023_render_created_at.py` (`down_revision = "0022_readiness_reports"`): `op.add_column` for each table, `sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)`; symmetric `downgrade`. Repair entries in `_repair_sqlite_schema_drift`: `ALTER TABLE segment_renders ADD COLUMN created_at TIMESTAMP` (same for `chapter_renders`, `export_packages`), guarded by the existing column-missing check pattern in that function.
- [ ] **Step 4: Switch every "latest" lookup to time ordering.** Replace `.order_by(X.id.desc())` with `.order_by(X.created_at.desc(), X.id.desc())` at: rendering.py:53, rendering.py:155, review.py:90, assembly.py active/history query (~:186), assembly.py `_resolve_inputs` (~:219), exporting.py `list_packages` (~:219) and `_active_render` (~:450), readiness.py chapter-audio lookup (~:490). In `_latest_successful` (rendering.py:187-196) add `.order_by(created_at, id)` to the query so `_tip`'s `tips[-1]`/`records[-1]` fallbacks become deterministic (chain-walk logic itself stays).
- [ ] **Step 5: Assembly revision assertion.** In `_resolve_inputs`, after selecting a segment's render, parse `json.loads(record.request_json)` and if `payload.get("revision") != segment.revision` raise `ValueError(f"Stale render for segment {segment.id}: render revision {payload.get('revision')} does not match segment revision {segment.revision}. Re-render before assembling.")`.
- [ ] **Step 6: Expose `createdAt`.** Add `created_at: datetime | None = None` (alias `createdAt`, copy the `PatchAttempt.createdAt` pattern) to `SegmentRender`, `ChapterRender`, `ExportPackage` in domain models; populate it wherever those models are constructed from records (rendering.py `_model` + the inline construction at :100-109, assembly.py, exporting.py).
- [ ] **Step 7: Write the failing stale-revision test.** In `test_assembly.py`: produce a chapter, then `PATCH /api/v1/segments/{id}` with new text (bumps `revision` without re-rendering), then invoke assembly directly (import `ChapterAssembler` and build it from the app's container — find how `create_app` exposes it; tests may construct `AppContainer` from the same `settings` fixture) and assert `ValueError` mentioning "Stale render".
- [ ] **Step 8: Run the two new tests + full suite** — `uv run pytest`. Also extend `test_issue_comment_and_selective_patch_preserve_render_history` (test_review.py:61) to assert the new chapter render's manifest contains the **patched** segment render id.
- [ ] **Step 9: Verify migration** — `ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db uv run alembic -c libs/db/alembic.ini upgrade head`.
- [ ] **Step 10: Lint/typecheck** — `uv run ruff check .` and `uv run mypy apps/api/src libs/domain-models/src libs/db/src`.
- [ ] **Step 11: Update docs** (`current-pipeline-behavior.md` render-selection wording; `db-schema.md` new columns), commit everything with `feat(db): time-ordered render/export selection with assembly revision guard`, merge `--no-ff` into `main`, push.

---

### Task 2 (G2): Patch forces a fresh re-render with the segment's real voice/direction

**Branch:** `feat/g2-patch-rerender`

**Problem:** `POST .../segments/{id}/patch` trusts the caller's `voiceProfileId`/`direction` verbatim; the frontend always sends the project narrator voice + a hardcoded default direction (`apps/web/app/project-dashboard.tsx:221`, `directionFor` at :32). It also never sets `force`, so the render cache (`rendering.py:44-56`) can return byte-identical audio — a silent no-op that still reports "patched".

**Files:**
- Modify: `libs/domain-models/src/echodraft_domain/models.py` — `SegmentPatchRequest` (~682-687)
- Modify: `apps/api/src/echodraft_api/production.py` — add public resolution helper
- Modify: `apps/api/src/echodraft_api/review.py:71-108` — `patch_segment`
- Modify: `apps/api/src/echodraft_api/rendering.py:32-43` — force-nonce in payload
- Modify: `apps/web/app/project-dashboard.tsx` — `patch()` handler; `apps/web/app/api.ts` — patch payload type
- Modify docs: `docs/pipeline/review/review-patch-workbench.md` (patch semantics)
- Test: `apps/api/tests/test_review.py` (3 new tests)

**Interfaces:**
- Consumes: Task 1's time-ordered selection (patched render must win "latest").
- Produces:
  - `SegmentPatchRequest.voice_profile_id: str | None = None` and `.direction: DirectionProfile | None = None` (overrides of the inherited required fields — omitted means "resolve server-side").
  - `ProductionService.resolve_voice_and_direction(project_id: str, segment_id: str) -> tuple[str, DirectionProfile]` — layering: segment production override → cast-resolved voice (`container.speaker_attributions.resolved_voice_profiles`) → `settings.narrator_voice_profile_id` (raise `ValueError("Set a narrator voice before patching.")` if none); direction: override → `SegmentDirectionRecord` → project default → blank `DirectionProfile(scopeType="segment", scopeId=segment_id)`. Reuse the existing private pieces (`_direction_for`, production.py:220-233) — do **not** duplicate the layering logic.
  - Patch **always** renders fresh: `patch_segment` builds `SegmentRenderRequest(voiceProfileId=resolved_voice, direction=resolved_direction, force=True, ...)`.
  - When `force=True`, `SegmentRenderer.render` adds `"forceNonce": uuid4().hex` to the hashed payload so a forced render always gets a distinct `render_key` (this is what makes Task 4's uniqueness index on succeeded `(segment_id, render_key)` safe).

**Steps:**

- [ ] **Step 1: Write the failing no-op test** (`test_review.py`): set up project → generate a render via `/generate` (existing `render_payload` helper), then call `/patch` with **only** `{"issueId": ...}` (no text change, no voice, no direction). Assert the response render id differs from the first render's id and `parentRenderId` equals the first render's id. Fails today (422 on missing required fields — which is itself the bug: the API forces the client to supply what the server should resolve).
- [ ] **Step 2: Write the failing voice-resolution test**: copy the cast setup from `apps/api/tests/test_speaker_attribution.py::test_speaker_attribution_review_and_production_voice_resolution` (character + voice profile + `CharacterVoiceAssignment` + approved attribution for the dialogue segment). Patch that segment with only `issueId`. Load the new render's `request_json`/metadata and assert `voiceProfileId` equals the **character's** voice profile id, not the narrator's.
- [ ] **Step 3: Write the failing direction-resolution test**: upsert a segment direction via the existing segment-direction endpoint (see `apps/api/src/echodraft_api/main.py` direction routes / `test_direction_studio.py` for the shape) with a distinctive value (e.g. `pace: 1.3`), patch with only `issueId`, assert the render's stored `direction.pace == 1.3`.
- [ ] **Step 4: Run all three, verify they fail** — `uv run pytest apps/api/tests/test_review.py -x`.
- [ ] **Step 5: Implement** — domain model field overrides; `resolve_voice_and_direction` on `ProductionService`; `patch_segment` resolves (honoring explicitly-supplied values as manual overrides when present), always sets `force=True`; force-nonce in `rendering.py` payload construction (insert before the hash at :43).
- [ ] **Step 6: Run the tests, verify pass; run full backend suite** — the two pre-existing patch tests in `test_review.py` still pass (they send explicit voice/direction — now treated as manual overrides).
- [ ] **Step 7: Frontend** — `project-dashboard.tsx` `patch()`: send only `{ issueId: issue.id }`; drop the `narratorVoiceProfileId` guard so patch works without reading production settings; update the payload type in `api.ts` (make `voiceProfileId`/`direction` optional). Remove `directionFor` if now unused. Run `npm run web:lint` and `npm run web:typecheck`.
- [ ] **Step 8: Full verification** (pytest, ruff, mypy, web lint+typecheck), update `review-patch-workbench.md` ("patch re-renders with the segment's resolved voice and direction and always produces fresh audio"), commit `feat(review): patch forces fresh re-render with resolved voice and direction`, merge `--no-ff`, push.

---

### Task 3 (G3): Fix the resolve-trap — readiness re-derives, auto-resolves, and re-surfaces

**Branch:** `feat/g3-readiness-resolve`

**Problem:** `ReadinessService._store_report` (readiness.py:587-591) counts a check out of "active" purely by its linked issue's status string. Once a user clicks Resolve/Ignore/Lock, the check is excluded forever even though `_collect_checks` keeps computing `status="failed"`. Nothing ever auto-resolves an issue whose condition was actually fixed, and patching never re-verifies anything.

**Target semantics:**
1. **"resolved" is a claim, re-verified every run:** in `ReadinessService.run`, when a draft still fails and its deduped issue has `status == "resolved"`, **reopen it** (set status `"open"`, and record `"reopened": true` in the check metadata). Resolved-but-still-failing can never hide.
2. **"ignored"/"locked" = accept-risk:** stays excluded from blocking, but is counted separately in the report summary as `"accepted"` and remains visible in the checks list (distinct, re-surfacing state — not silently gone).
3. **Auto-resolve on pass:** when a draft **passes** and an issue row exists for its dedupe key with status other than `"resolved"`, set it to `"resolved"` automatically.
4. **Patch re-verifies:** after a successful patch render, if the patched issue's metadata carries a `segmentRenderId` (i.e. it's a render-QA issue), and the *new* render's QA produced no open issue of the same category, auto-resolve the patched issue (add `"resolvedBy": "rerender"`, `"newRenderId": ...` to its metadata).

**Files:**
- Modify: `apps/api/src/echodraft_api/readiness.py` — `run` (55-100), `_store_report` (584-619)
- Modify: `libs/db/src/echodraft_db/review.py` — add `issue_by_dedupe_key(key: str) -> IssueRecord | None` and reuse existing `update_issue`; extend `update_issue` to accept a metadata merge (or add `merge_issue_metadata`)
- Modify: `apps/api/src/echodraft_api/review.py` — `patch_segment` (auto-resolve hook after render+assemble)
- Modify: `apps/web/app/components/review/ReadinessReportPanel.tsx` — separate "Accepted risks" section listing accepted checks; button label "Ignore" → "Accept risk"; keep sending `"ignored"` on the wire
- Modify: `apps/web/app/project-dashboard.tsx` — after `setReadinessIssue` and after `patch()`, re-run readiness (`runReadiness`) instead of/in addition to the optimistic local mutation, so the badge is derived server-side
- Modify docs: `docs/pipeline/qa/readiness-qa.md` (the "statuses survive reruns" paragraph at :31-37 must be rewritten to the new semantics)
- Test: `apps/api/tests/test_readiness.py`, `apps/api/tests/test_review.py`

**Interfaces:**
- Consumes: Task 2 (patch produces a genuinely fresh render, so "re-verify on patch" is meaningful).
- Produces: report `summary` gains `"accepted": <int>`; check metadata may carry `"reopened": true`. Issue status vocabulary (unchanged strings, new semantics): `open`, `resolved` (auto-verified), `ignored`/`locked` (accept-risk).

**Steps:**

- [ ] **Step 1: Failing test — reopen.** In `test_readiness.py`: run readiness on a project with a failing check (the existing first test's setup produces several), PATCH its issue to `"resolved"`, re-run readiness, assert the check's `resolutionStatus` is back to `"open"`, the issue row is `"open"`, and the report status/score still reflect the failure.
- [ ] **Step 2: Failing test — accept-risk counted separately.** PATCH an issue to `"ignored"`, re-run, assert check keeps `resolutionStatus == "ignored"`, is excluded from `blocking`/`warnings`, and `summary["accepted"] == 1`. (Adapt the existing `test_readiness_report_persists_checks_and_issue_resolution` — its ignored-persistence assertion survives, its implicit "excluded forever" framing goes.)
- [ ] **Step 3: Failing test — auto-resolve on pass.** Pick a check that can be made to pass (e.g. the rights-declaration or narrator-voice check — set the missing field via its API), re-run readiness, assert the previously-created issue's status is now `"resolved"`.
- [ ] **Step 4: Failing test — patch auto-resolves render-QA issues.** In `test_review.py`: create a render whose QA raises an issue (e.g. `very_short_duration` — the mock provider's output can be made short via a very short segment text; check how existing tests trigger QA issues in `test_qa_issues_are_durable_and_deduplicated_per_render`), then patch the segment with longer text so the new render passes; assert the original issue is `"resolved"` with `resolvedBy: "rerender"` metadata.
- [ ] **Step 5: Run all four, verify they fail.**
- [ ] **Step 6: Implement backend** per the four target semantics. In `run()`, passing drafts also need their dedupe key computed (same format string) to find auto-resolvable issues. `_store_report`: `active` = failing ∧ resolution in `{None, "open"}`; `accepted` = failing ∧ resolution in `{"ignored", "locked"}`; summary gains `"accepted"`; status formula unchanged (driven by `active` only).
- [ ] **Step 7: Run backend suite + fix the encoded-trap test** (`test_readiness_report_persists_checks_and_issue_resolution` now asserts the new contract).
- [ ] **Step 8: Frontend** — Accepted-risks section + relabel + server-derived refresh after resolve/patch. `npm run web:lint`, `npm run web:typecheck`.
- [ ] **Step 9: Full verification, update `readiness-qa.md`, commit `feat(qa): readiness re-derives state, auto-resolves fixed checks, accept-risk resurfaces`, merge `--no-ff`, push.**

---

### Task 4 (G12): SQLite hardening, bounded job executor, CI + schema-drift check

**Branch:** `feat/g12-db-hardening-ci`

**Problem:** No WAL/busy_timeout/FK enforcement (`database.py:12-19` sets only `check_same_thread=False`); unbounded thread-per-job (`jobs.py:31,42`); a TOCTOU race in `SegmentRenderer.render` (parent selected at rendering.py:83-84, inserted at :96-98 in a different session) can fork the append-only chain; no uniqueness backstop; no CI; nothing detects Alembic-vs-models drift.

**Files:**
- Modify: `libs/db/src/echodraft_db/database.py` — engine pragmas, session rollback-on-exception, repair entries
- Modify: `apps/api/src/echodraft_api/jobs.py` — bounded executor
- Modify: `apps/api/src/echodraft_api/config.py` — `max_concurrent_jobs: int = 2` (env `ECHODRAFT_MAX_CONCURRENT_JOBS`); `apps/api/src/echodraft_api/container.py` — pass it to `InProcessJobRunner`
- Modify: `apps/api/src/echodraft_api/rendering.py` — per-segment render lock; `apps/api/src/echodraft_api/assembly.py` — per-chapter assemble lock
- Modify: `libs/db/src/echodraft_db/models.py` — partial unique index on `segment_renders`
- Create: `libs/db/alembic/versions/0024_segment_render_uniqueness.py`
- Create: `.github/workflows/ci.yml`
- Create: `apps/api/tests/test_migrations.py` (schema-drift check)
- Modify docs: `docs/operations/alpha-operations.md` (CI + concurrency notes), `docs/domain/db-schema.md` (index)
- Test: `apps/api/tests/test_foundations.py` additions + `test_migrations.py`

**Interfaces:**
- Consumes: Task 1's migration `0023` (drift check covers it) and Task 2's force-nonce (makes the uniqueness index safe under forced re-renders).
- Produces: engine-level PRAGMAs for every connection; `InProcessJobRunner(repository, max_workers)`; serialized per-segment renders; unique index `uq_segment_renders_succeeded_key` on `(segment_id, render_key)` where `status='succeeded'`; CI gating merges; drift test that fails when models and migrations diverge.

**Steps:**

- [ ] **Step 1: Failing pragma test** (`test_foundations.py`): build `Database(sqlite url)`, open a connection, assert `PRAGMA journal_mode` returns `wal`, `PRAGMA foreign_keys` returns 1, `PRAGMA busy_timeout` returns 30000.
- [ ] **Step 2: Implement pragmas.** In `database.py`, for `sqlite` URLs add `connect_args={"check_same_thread": False, "timeout": 30}` and register a connect-event listener:
  ```python
  from sqlalchemy import event

  if url.startswith("sqlite"):
      @event.listens_for(self.engine, "connect")
      def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
          cursor = dbapi_connection.cursor()
          cursor.execute("PRAGMA journal_mode=WAL")
          cursor.execute("PRAGMA foreign_keys=ON")
          cursor.execute("PRAGMA busy_timeout=30000")
          cursor.execute("PRAGMA synchronous=NORMAL")
          cursor.close()
  ```
  (WAL on `:memory:` degrades gracefully to `memory` journal mode — assert `wal` only for file DBs.) Also make `Database.session()` roll back on exception before closing. **Watch for FK fallout:** enabling `foreign_keys=ON` may surface latent test failures (deletes/orphans that used to slip through) — fix those properly, don't drop the pragma.
- [ ] **Step 3: Failing executor test**: `InProcessJobRunner` with `max_workers=1`; submit two jobs whose operations block on a `threading.Event`; assert the second stays `PENDING` while the first runs (bounded), then release and assert both `SUCCEEDED`.
- [ ] **Step 4: Implement bounded executor** — replace both `Thread(...).start()` sites with a shared `ThreadPoolExecutor(max_workers=...)` created in `__init__`; jobs stay `PENDING` until `run_inline` starts (it already transitions to `RUNNING`). Wire `max_concurrent_jobs` setting (default 2) through `container.py`.
- [ ] **Step 5: Render serialization + uniqueness backstop.** In `rendering.py`, add a module-level lock registry (`_render_locks: dict[str, threading.Lock]` + guard lock, keyed by `segment_id`); hold the segment's lock across cache-check → parent-selection → insert in `render()`. Same pattern per `chapter_id` around `ChapterAssembler.assemble`. Then add to `SegmentRenderRecord.__table_args__` a partial unique index:
  ```python
  Index(
      "uq_segment_renders_succeeded_key",
      "segment_id", "render_key",
      unique=True,
      sqlite_where=text("status = 'succeeded'"),
  )
  ```
  Migration `0024_segment_render_uniqueness.py` (`down_revision = "0023_render_created_at"`): first defuse pre-existing duplicates by marking all but the newest (by `created_at`, then rowid) of each `(segment_id, render_key, status='succeeded')` group as `status='superseded'` (UPDATE, never DELETE — history is append-only), then `op.create_index(..., unique=True, sqlite_where=...)`. Mirror both steps idempotently in `_repair_sqlite_schema_drift` (`CREATE UNIQUE INDEX IF NOT EXISTS` after the same dedupe UPDATE). Concurrency test: two threads calling `SegmentRenderer.render` (mock provider) for the same segment with `force=True`; assert afterwards the succeeded-render parent chain is linear (no two renders share a `parent_render_id`) and no `database is locked` error was raised.
- [ ] **Step 6: Schema-drift test** (`apps/api/tests/test_migrations.py`): create a tmp SQLite file; run Alembic programmatically (`alembic.config.Config(str(repo_root / "libs/db/alembic.ini"))`, set `ECHODRAFT_DATABASE_URL` env — `libs/db/alembic/env.py:12-13` reads it — then `alembic.command.upgrade(cfg, "head")`); reflect the result and compare with `Base.metadata` via `alembic.autogenerate.compare_metadata` on a `MigrationContext`; assert the diff list is empty with a readable failure message. **If this reveals existing drift** (models changed without migrations — likely given the hand-maintained repair function), write catch-up migration(s) `0025_...` to close it; the test must pass honestly, never by weakening the comparison. Exclude Alembic's own `alembic_version` table if it appears in the diff.
- [ ] **Step 7: CI workflow** `.github/workflows/ci.yml` — trigger on `push` to `main` and `pull_request`; jobs:
  1. `backend`: `astral-sh/setup-uv@v5` (installs uv; let it read `requires-python`), `uv sync --locked --all-packages --dev` (verify flag names against uv docs if sync fails), then `uv run pytest`, `uv run ruff check .`, `uv run mypy apps/api/src libs/domain-models/src libs/db/src`.
  2. `migrations`: setup-uv, `mkdir -p .tmp`, `ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/ci-migration.db uv run alembic -c libs/db/alembic.ini upgrade head`, then `... downgrade base`, then `... upgrade head` again (round-trip).
  3. `web`: `actions/setup-node@v4` (node 22, cache npm), `npm ci`, `npm run web:lint`, `npm run web:typecheck`.
  4. `smoke`: needs `backend` + `web`; setup-uv + setup-node, `npm ci`, `uv sync --locked --all-packages --dev`, `npx playwright install --with-deps chromium`, `npm run web:test:smoke`. If the smoke job proves environmentally flaky on the runner, keep it as a separate non-required job (`continue-on-error: false` first; only relax with an explicit code comment explaining why) — do not silently delete it.
- [ ] **Step 8: Full local verification** (pytest incl. new tests, ruff, mypy, migration round-trip, web lint/typecheck). Commit `feat(infra): SQLite hardening, bounded job executor, CI with schema-drift gate`, merge `--no-ff`, push, then **watch the first CI run on GitHub** (`gh run watch` or `gh run list --branch main`) and fix any runner-environment failures in follow-up commits on the same branch pattern (branch → fix → merge → push) until CI is green.

---

## Post-plan verification (whole phase)

After all four tasks: run the complete verification battery once more from a clean `main` checkout, then dispatch a whole-branch code review over `merge-base(main@start-of-phase, main)`. Phase 0 exit criteria (roadmap): a patched segment always reaches the exported chapter; readiness never reports "ready" while a check still fails; no `database is locked` under concurrent jobs; every merge gated by CI.
