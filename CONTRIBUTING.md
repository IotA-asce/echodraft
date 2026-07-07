# Contributing to Echodraft 🎙️

Thanks for your interest in contributing!

Echodraft is a **local-first AI audiobook production system** that turns
rights-cleared manuscripts into editable, patchable, multi-voice chapter
drafts — segment by segment, not one giant TTS job.

This is alpha software with an ambitious v2 roadmap, and there is a lot of
room to contribute: code, documentation, hands-on listening evaluation, bug
reports, and hardware-diverse TTS testing all matter.

## Where to start

Read in roughly this order:

1. [`docs/README.md`](docs/README.md) — the documentation index and reading
   order for the current (alpha) implementation.
2. The [v2 target-product documentation suite](docs/README.md#target-product-v2-documentation-suite)
   — the design for the complete product, starting with
   [`product-vision-v2.md`](docs/product/product-vision-v2.md).
3. [`docs/plans/2026-07-07-v2-implementation-roadmap.md`](docs/plans/2026-07-07-v2-implementation-roadmap.md)
   — the master implementation plan that sequences the v2 suite into
   dependency-ordered workstreams (W0–W9). This is the best map of "what's
   available to work on."
4. [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) — the authoritative
   repo operating rules (branching, verification, commit workflow).
   `AGENTS.md` wins if the two ever disagree.

## Ways to contribute

### Code — pick a roadmap workstream

The [v2 implementation roadmap](docs/plans/2026-07-07-v2-implementation-roadmap.md)
breaks the whole program into dependency-ordered workstreams. Each one cites
an owning design doc that remains the source of truth for *what* to build:

| Workstream | One-liner | Owning doc |
|---|---|---|
| **W0** | UI quick wins — memoization, TanStack Query, scoped polling to stop "page unresponsive" incidents | [frontend-architecture.md](docs/ui/frontend-architecture.md) |
| **W1** | Eval baseline harness — golden corpus + metrics so extraction changes are measured, not assumed | [extraction-pipeline-v2.md](docs/architecture/extraction-pipeline-v2.md) |
| **W2** | Orchestrator core — resumable, checkpointed DAG runner, inference cache, SSE event bus, adaptive LLM pool | [target-architecture.md](docs/architecture/target-architecture.md) |
| **W3** | Extraction v2 — LLM-first, parallel, cached ingestion/structure/cast/attribution/direction, gated against the W1 baseline | [extraction-pipeline-v2.md](docs/architecture/extraction-pipeline-v2.md) |
| **W4** | Automatic casting — fully automatic narrator/character voice assignment from traits and a real voice catalog | [automatic-casting-v2.md](docs/pipeline/casting/automatic-casting-v2.md) |
| **W5** | Expressive TTS — audible directed emotion, new-voice synthesis, engine tiering, parallel rendering | [tts-engine-strategy.md](docs/pipeline/tts/tts-engine-strategy.md) |
| **W6** | Generative sound design — AI-generated ambience/music/SFX, auto-placed, never masking dialogue | [generative-sound-design.md](docs/pipeline/assembly/generative-sound-design.md) |
| **W7** | UI overhaul — monochrome design system, real routes, virtualization, SSE adoption, monolith retirement | [frontend-architecture.md](docs/ui/frontend-architecture.md), [design-system.md](docs/ui/design-system.md) |
| **W8** | Desktop packaging — self-contained signed installers with bundled dependencies and managed model downloads | [cross-platform-strategy.md](docs/platform/cross-platform-strategy.md) |
| **W9** | Mobile — companion mode, then a native React Native/Expo app | [cross-platform-strategy.md](docs/platform/cross-platform-strategy.md) |

Check [`docs/progress-tracker.md`](docs/progress-tracker.md) before starting
so you don't duplicate in-flight work, and open an issue (or comment on an
existing one) to claim a task before starting anything larger than a small
fix.

### Documentation

The `docs/` tree is the source of truth for design and implementation. Fixes
to inaccuracies, gaps in the reading order, or clarifications learned while
implementing are all welcome — see the
[directory map](docs/README.md#directory-map) for where a given topic lives.

### Golden-corpus labeling / listening evaluation

This is uniquely valuable for an audiobook project and hard to source
elsewhere. Extraction and casting quality are measured against a golden
corpus of hand-labeled, public-domain text (see
[W1](docs/plans/2026-07-07-v2-implementation-roadmap.md) and
[`quality-evaluation-v2.md`](docs/pipeline/qa/quality-evaluation-v2.md)). You
can help by:

- Hand-labeling speaker attribution (named speaker / narrator / unknown) on
  public-domain prose fixtures.
- Doing structured **listening evaluation** — blind A/B comparisons of
  directed vs. metadata-only renders, flagging where delivery, pacing, or
  sound design breaks the "supports, never masks" bar.
- Reporting where automatic casting or attribution feels wrong on your own
  rights-cleared manuscripts.

### Bug reports

File issues using the bug report template. Please **do not attach copyrighted
manuscripts** — describe the manuscript's structure (length, format,
language) instead, or reduce the repro to a public-domain excerpt.

### TTS / audio model bake-off testing

Echodraft evaluates and tiers local TTS/audio-generation engines across very
different hardware, from CPU-only laptops to GPU workstations. If you have
hardware outside the common range — Apple Silicon, older CPUs, various
GPU/VRAM sizes, different Linux distributions — running the bake-off harness
(see [`tts-engine-strategy.md`](docs/pipeline/tts/tts-engine-strategy.md),
workstream W5.3) and reporting results is directly useful.

## Development setup

```bash
git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

Start the API (repo root, first terminal):

```bash
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

Start the dashboard (second terminal):

```bash
npm run web:dev
```

Then open `http://localhost:3000` (dashboard) and `http://localhost:8000/docs`
(interactive API docs). See the README's
[Quick start](README.md#quick-start) and [Platform setup](README.md#platform-setup)
sections for Windows/macOS/Linux system-package details.

## The workflow contract

Every change in this repo follows the golden implementation workflow defined
in `AGENTS.md` / `CLAUDE.md`:

1. **Create a feature branch** from the current target branch. Never commit
   directly to `main`.
2. Implement only what's in scope.
3. Run the relevant verification commands (below).
4. Commit with a clear, conventional message (`feat:`, `fix:`, `docs:`,
   `refactor:`, `test:`, `chore:`, …).
5. Merge back into the target branch with `--no-ff`, matching repo history.
6. Push.

### Verification commands

Run as many as are relevant to your change; if one can't run, say so
explicitly in your PR. These are the same checks CI runs — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

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

Migrations (only if persistence changed, against a disposable DB):

```bash
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db \
  uv run alembic -c libs/db/alembic.ini upgrade head
```

### "Done" means

- Implemented within scope.
- Verified with the applicable commands above.
- Docs updated if behavior changed.
- [`docs/progress-tracker.md`](docs/progress-tracker.md) updated in the same
  branch/commit if a roadmap or gap-analysis item changed status.
- Committed, merged, and pushed.

## PR guidelines

- Keep scope small — one workstream task or one logical change per PR.
- Link the design doc and/or workstream task in the description (e.g.
  "implements W3.1, see `docs/plans/2026-07-07-v2-implementation-roadmap.md`").
- Include the verification output you ran, or state clearly which checks you
  couldn't run and why.
- Call out any behavior change that needs a docs update, and make that
  update in the same PR.
- Note any roadmap status change that needs a `docs/progress-tracker.md`
  update.

## Engineering constraints

Contributions must respect the project's core invariants:

- **Segment-first.** The segment is the atomic editable/renderable unit —
  don't collapse chapter/scene/segment granularity, even for speed.
- **Manifest-driven.** Update manifests whenever pipeline inputs or outputs
  change.
- **Append-only history.** Segment and chapter render history is never
  overwritten, only appended to.
- **No audio blobs in the DB.** SQLite (and any relational DB) holds
  metadata and filesystem paths only; artifacts live on disk.
- **Local-first.** No mandatory cloud services in MVP code; cloud is opt-in
  only, never required for the happy path.
- **`test-assets/` stays local.** It's git-ignored by design — never stage,
  commit, or push files from it.

## Questions

Use [GitHub Discussions](https://github.com/IotA-asce/echodraft/discussions)
for questions and open-ended conversation, and
[GitHub Issues](https://github.com/IotA-asce/echodraft/issues) for concrete
bugs or feature proposals.
