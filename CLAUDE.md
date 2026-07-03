# CLAUDE.md

Guidance for Claude Code when working in this repository. This file distills the
authoritative rules in [`AGENTS.md`](AGENTS.md) — if the two ever disagree,
`AGENTS.md` wins.

## What this is
Echodraft is a **local-first AI audiobook production system** that turns
rights-cleared manuscripts into editable, patchable, multi-voice chapter drafts.
Core priorities, in order:
1. segment-first architecture (a segment is the atomic editable/renderable unit)
2. manifest-driven pipeline
3. patchability over one-shot generation
4. local-first privacy (no mandatory cloud services)
5. conservative, tasteful audio production

## Golden implementation workflow (do not skip)
For every change, follow this exact sequence:
1. **Create a feature branch** from the current target branch. **Never commit directly to `main`.**
2. Implement only what is in scope.
3. Run the relevant verification commands (see below).
4. Commit with a clear, conventional message.
5. Merge the feature branch back into the target branch (`--no-ff`, matching repo history).
6. Push the target branch (and the feature branch when useful for review/traceability).

The repo owner has authorized pushing completed, **verified** work to `origin`.
Do **not** force-push, rewrite history, or stage unrelated user changes. Do not
merge unverified changes unless the user explicitly says to.

## Verification commands
Run as many as are relevant to the change; if a check can't run, say so explicitly before merge.

Backend (from repo root):
```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
```
Frontend:
```bash
npm run web:lint
npm run web:typecheck
npm run web:test:smoke        # requires: npx playwright install chromium
```
Migrations (against a disposable DB when persistence changes):
```bash
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db \
  uv run alembic -c libs/db/alembic.ini upgrade head
```

"Done" means: implemented, verified where applicable, docs updated if behavior
changed, committed, merged, and pushed.

## Repo layout
- `apps/api` — FastAPI application and pipeline services
- `apps/web` — Next.js local dashboard
- `libs/domain-models` — shared Pydantic API/domain models
- `libs/db` — SQLAlchemy repositories and Alembic migrations
- `services/*` — reserved domain-service placeholders
- `docs/` — architecture, product, API, and operating specs
- `plans/`, `implement/` — roadmap and stage-by-stage briefs
- `test-assets/` — **git-ignored** local-only fixtures; never stage/commit/push

## Engineering constraints
- Keep changes modular and local-first; avoid cloud-only assumptions in MVP code.
- Preserve **append-only** segment and chapter render history.
- Never store audio blobs in SQLite or any relational DB — DB holds metadata and
  paths only; artifacts live on the filesystem.
- Keep the segment as the atomic editable/renderable unit.
- Update manifests whenever pipeline inputs or outputs change.

## Environment notes
- Python 3.12 is the known baseline; use `uv` for the workspace.
- Shell here is PowerShell (primary) plus a POSIX Bash tool — use each tool's own syntax.
- Config is read from the process environment (`ECHODRAFT_*`); defaults work with no exports.
