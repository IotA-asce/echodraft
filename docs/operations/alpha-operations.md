# Alpha Operations

## Recovery

- Jobs interrupted by an application restart are marked failed; restart the workflow from its persisted source, render, or chapter artifact.
- Kokoro setup runs as a local job. If it fails, use the dashboard's **Repair setup** action after checking network access, disk capacity, and whether Python can create virtual environments and install wheels.
- Chapter production runs expose per-segment progress in the dashboard. Retry a failed chapter after correcting its local adapter, narrator selection, or source segment; valid prior renders are retained.
- Validation errors require correcting the request. Filesystem errors require checking local disk capacity and permissions.
- Do not include manuscript text or generated audio in bug reports unless the tester explicitly consents.

## Triage

Use `blocking` for an inability to import, render, assemble, patch, or export. Include reproduction steps, job ID, app version, and the redacted error message.

## Concurrency

- SQLite runs in WAL mode with `busy_timeout=30000` and `foreign_keys=ON` on every connection, so concurrent readers and a single writer coexist without `database is locked` errors under normal alpha load.
- Background jobs run on a bounded thread pool. The worker count is `ECHODRAFT_MAX_CONCURRENT_JOBS` (default `2`); extra submissions stay `queued` until a worker frees up. Lower it to `1` on constrained machines; raise it only if local TTS/assembly work is I/O-bound.
- Segment renders are serialized per segment and chapter assembly per chapter, so a burst of duplicate requests cannot fork the append-only render history. A partial unique index (`uq_segment_renders_succeeded_key`) is the database-level backstop; forced re-renders remain safe because each carries a distinct render key.

## Continuous integration

- `.github/workflows/ci.yml` gates `main` and every pull request with four jobs: `backend` (pytest, ruff, mypy), `migrations` (Alembic upgrade → downgrade base → upgrade round-trip), `web` (lint, typecheck), and `smoke` (Playwright, gated behind `backend` + `web`).
- The app bootstraps schema via `create_all` plus the SQLite repair pass, not Alembic, so `apps/api/tests/test_migrations.py` compares the Alembic head against `Base.metadata` and fails on any drift. When models change, add a migration in the same PR; never weaken that comparison.

## Known Limits

- In-process jobs cannot resume mid-operation.
- MP3 export requires local FFmpeg with an MP3 encoder. M4B remains unsupported.
- Sound Design accepts local WAV assets for ambience, music, and SFX. Clean narration remains the stable default; light and dramatized mixes are explicit assembly actions.
- Mock TTS is intentionally silent. Managed Kokoro ONNX setup downloads local runtime assets only after explicit user action and exposes fixed selectable preset voices; it does not create new custom voices. Direction Studio controls are retained in render metadata, with current Kokoro adapters applying supported pace data and reporting unsupported expressive controls.
- Piper and XTTS-v2 are local-only provider paths. Piper requires a local executable and model file. XTTS-v2 requires a local Python runtime, reference WAV, and explicit reference-voice consent before synthesis starts.
- Render queue rows are metadata-only status records. Diagnose failures from the queue row error, the owning job, and the segment render metadata path; do not delete successful prior renders when retrying.
- Readiness QA writes snapshot reports and linked review issues. `resolved`, `ignored`, and `locked` issue statuses are preserved across reruns.
- Managed Kokoro setup is CPU-oriented. GPU/provider tuning and automatic OS package manager repair are out of scope.
- Text PDFs import directly. Scanned PDFs require `pdftoppm` from Poppler and English Tesseract data on `PATH`; OCR runs locally at 200 DPI and is capped at 150 low-text pages per import.
