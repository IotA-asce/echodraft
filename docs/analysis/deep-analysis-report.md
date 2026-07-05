# Echodraft — Deep Analysis & Improvement Report

**Date:** 2026-07-03
**Updated:** 2026-07-05
**Scope:** Full system — FastAPI backend (~11.3k LOC Python), Next.js dashboard (~3.5k LOC TS/TSX), SQLAlchemy/SQLite data layer, local‑AI/model‑center tooling, and the end‑to‑end production pipeline.
**Method:** The codebase was mapped, then analyzed in parallel across seven subsystems by focused sub‑agents (code‑structure lens and product‑quality lens), with the highest‑impact findings independently verified against source. File:line references throughout point to specific evidence.

> **Completion update:** this report is now a historical baseline plus completion record. The top engineering findings that fed the Phase 0-4 roadmap have been implemented, verified, merged, and pushed. File/line references in the historical sections reflect the 2026-07-03 codebase and should not be read as current defects without re-checking current `main`.

> **Corpus:** `apps/api/src/echodraft_api` (27 modules; `main.py` 1685 LOC, `structure_parsing.py` 1637 LOC), `apps/web/app` (40+ components), `libs/db` (45 tables, 22 migrations), `libs/domain-models` (~100 Pydantic models). No import cycles. Services under `services/` are empty placeholders.

---

## 1. Executive summary

Echodraft is an unusually **well‑architected local-first audiobook production system**. The core design ideas — segment‑as‑atomic‑unit, append‑only render history, manifest‑driven stages, evidence‑first review, deterministic‑with‑optional‑LLM parsing, and strict fail‑closed local providers — are coherent, consistently applied, and genuinely differentiated from one‑shot TTS tools. Domain logic is cleanly separated into per‑concern service modules, the DI container is simple, and the documentation set is extensive.

The original gap between the 2026-07-03 state and "produces a flawless, publishable audiobook" came down to a handful of **correctness bugs** and **quality ceilings** that were individually fixable but invisible behind green "ready" signals:

1. **Patched audio could silently fail to reach the export** — closed by deterministic render/export ordering and stale revision guards.
2. **Direction Studio controls were not audible for key providers** — closed by truthful capability metadata and supported control transmission.
3. **Final audio was capped at 16 kHz mono** — closed by the 44.1 kHz mastered pipeline.
4. **SQLite/job concurrency was unsafe** — closed by local DB/worker hardening and render cache serialization.
5. **QA was thinner than documented** — closed by real audio QA, live readiness, scoped blockers, optional ASR word-match, transcript review, and listened approval.

The strong bones identified in the original report are now backed by the completed trust, audio, algorithmic, and workflow phases. Remaining work is optional polish, scale hardening, or broader market expansion.

---

## 2. System overview & operational flow

```
Create project (rights gate)
  → Import (TXT/MD/DOCX/EPUB/PDF+OCR) → clean-text → canonical.md + manifest
  → Structure extract (parser v0.4.0): blocks → chapters → scenes → quote-aware atoms → sentence-safe segments
        (+ optional bounded Ollama refinement, validated & rejected-to-deterministic on any violation)
  → Cast discovery + speaker attribution (deterministic + optional LLM, review-gated)
  → Voice setup (mock / Kokoro managed / Piper / consent-gated XTTS-v2) + Direction inference
  → Produce chapter: render stale/missing segments → append immutable SegmentRender → assemble ChapterRender (+optional ambience mix)
  → Readiness QA + transcript review → Review & patch (fix one line, re-render, reassemble, approve)
  → Export WAV/MP3/M4B package (manifest + lineage + checksums + optional retail sample)
```

**Composition.** `create_app()` (`main.py`) builds a single `AppContainer` dataclass (`container.py:54-82`) holding one instance of every repository plus the artifact store, TTS settings/adapter, and an in‑process job runner. There is **no `Depends()`‑based DI** — every route reads `request.app.state.container` directly (~80 call sites) and constructs a fresh stateless service (`IngestionService(container)`, `SegmentRenderer(container)`, …) per request. Long work is submitted to `InProcessJobRunner`, which spawns a **daemon `threading.Thread` per job** and returns `202`; clients poll `GET /api/v1/jobs/{id}`.

**Storage split (a real strength).** SQLite holds only metadata and path strings; all audio/manifests/waveforms live on the filesystem in a per‑project tree. Render history is genuinely append‑only (`SegmentRenderRecord` never updated; new rows link via `parent_render_id`). The single artifact read gateway (`get_artifact`, `main.py:455-464`) correctly containment‑checks resolved paths, and upload endpoints strip filenames to `Path(...).name` — path‑traversal handling is done right.

**Operational posture.** Local‑first, single‑user, loopback‑bound by default. Jobs are honestly non‑durable: `reconcile_interrupted()` fails any job left `RUNNING` after a crash with guidance rather than pretending to resume (`repository.py:255-268`).

---

## 3. Cross‑cutting themes

These patterns recurred across subsystems and became Phase 0-4 programs of work. Their roadmap status is now:

| Theme | Roadmap status | Current reading |
|---|---|---|
| **"Compute then discard"** | Closed | Direction, pauses, evidence, active-speaker rosters, structure metadata, and voice facets are delivered into render/review paths |
| **Ordering by random UUID** | Closed | Latest render/export selection is deterministic and stale revision checks protect assembly/export |
| **Green signal ≠ true state** | Closed | Readiness re-derives live state, accepted risks re-surface, patch rerenders are forced, and approvals bind to active renders |
| **Unbounded concurrency over unhardened SQLite** | Closed | SQLite and render-cache hardening are included in the completed trust foundation |
| **Contract kept in sync by hand** | Mitigated | Domain/API models, tests, and schema drift checks reduce drift risk; deeper OpenAPI codegen remains optional |
| **English‑only, keyword heuristics** | Mitigated | Baseline language detection, matter classification, container signals, and prosody/footnote handling are implemented; language-adaptive OCR/name/TTS remains optional polish |
| **Pure‑Python per‑sample audio DSP** | Mitigated | The 44.1 kHz mastering/audio QA path is implemented; deeper performance optimization can continue as scale work |
| **No CI / automated gate** | Closed | The workflow now includes validation and schema drift checks |
| **Docs drifted from code** | Mitigated | README, progress tracker, and pipeline docs have been updated through the completed roadmap |

---

## 4. Resolved top findings

Original findings ranked by impact on "a correct, publishable audiobook"; all are now resolved or mitigated by the completed roadmap.

| # | Original severity | Finding | Completion status |
|---|---|---|---|
| 1 | Critical | Patch may not reach export | Closed by deterministic latest ordering, timestamps, lineage, and stale revision guards |
| 2 | Critical | Direction controls not audible | Closed by truthful engine capabilities and supported control transmission |
| 3 | High | 16 kHz mono quality ceiling | Closed by 44.1 kHz mastered audio baseline |
| 4 | High | Unsafe concurrency over SQLite | Closed by SQLite/worker hardening and serialized render cache rechecks |
| 5 | High | QA weaker than documented; issues never auto-resolve; export blocked project-wide | Closed by real audio QA, live readiness, auto-resolution, scoped blockers, ASR, transcript review, and approvals |
| 6 | High | No CI and no schema-drift guard | Closed by validation and schema drift workflow |
| 7 | High | Render fingerprint incomplete | Mitigated by stale-render lineage/fingerprints across provider, direction, pronunciation, voice, and text inputs |
| 8 | Medium | API monolith and exception handling debt | Post-roadmap maintainability polish, not a Phase 0-4 blocker |

---

## 5. Subsystem deep analysis

This section is preserved as the 2026-07-03 engineering baseline that generated the roadmap. Treat the "Issues" and "Recommendations" lists below as historical source material unless they are repeated in the completion sections above.

### 5.1 Backend API & composition

**Strengths.** Correct path‑traversal containment and filename stripping everywhere artifacts are read/written; honest non‑resumable job handling with a strict `Job` state machine; a compensating rollback of the artifact dir if project‑insert fails (`main.py:466-477`); appropriate use of sync `def` handlers (Starlette thread‑pools them) for blocking SQLAlchemy/FS work; structured logging with an `x-request-id` correlation id; business logic already lives outside `main.py`.

**Issues.**
- **Critical (trust boundary):** no authn/authz on any route and permissive CORS (`allow_methods=["*"]`). Defensible for a loopback single‑user tool (`run()` binds `127.0.0.1`), but nothing *enforces* loopback, and endpoints like `create_sound_asset_from_path` (`main.py:1281-1308`) read an arbitrary absolute filesystem path from the request body, while `remove_project_layout` deletes. Document (and ideally enforce via a startup check / `--allow-remote` flag) the trust boundary; consider a local shared‑secret header.
- **High:** unbounded job concurrency (`jobs.py:27-43`) for a CPU/GPU‑bound workload; `JobState.CANCELLED` exists in the transition table but is never wired to any endpoint (half‑built cancellation).
- **High:** jobs cannot durably resume — the operation is an in‑memory closure, never serialized. A durable queue keyed off persisted entity ids would be a real (larger) redesign.
- **Medium:** inconsistent existence checks (`list_chapters`/`list_scenes`/`list_segments` return `[]` for a non‑existent parent instead of 404); two `async def` handlers (`import_source` `main.py:493-513`, `upload_sound_asset` `main.py:1315-1338`) do blocking disk I/O directly on the event loop; services `new`'d per request instead of living on the container; no upload size limits (`await file.read()` buffers whole file); `app = create_app()` at import time opens the real DB as an import side effect.
- **Low:** hardcoded CORS origins not sourced from settings; no pagination on any list endpoint; failed‑request path never sets the `x-request-id` response header.

**Recommendations.** Split `main.py` into `routers/` + a `presenters.py` and introduce `Depends(get_container)` **(L)**; global exception handler layer **(M)**; bounded `ThreadPoolExecutor` + wire cancellation **(M)**; fix the two blocking async handlers **(S)**; consistent 404 policy **(S)**; env‑configurable CORS + upload caps **(S)**.

### 5.2 Ingestion & structure parsing

**Strengths.** Source‑preserving by construction — atoms/segments never accept LLM‑generated *text*, only ids/hints/confidence, enforced end‑to‑end (`structure.py:296-333`). Deterministic‑first, LLM‑optional with strict validation and rejection‑to‑deterministic on any violation. Rigorous offset validation (`validate_atom_offsets`, `structure_parsing.py:219-285`). Content‑derived stable segment ids let user locks survive re‑extraction (`repository.py:368-489`). Good per‑page (not per‑document) PDF OCR decisioning with a sensible 150‑OCR‑page cap. Solid tests for quote/apostrophe handling, mixed dialogue, honorific aliases, and invalid‑LLM rejection.

**Issues.**
- **High — dead feature:** repeated header/footer removal splits on `\f` (`cleaning.py:109-149`) but nothing in the pipeline ever emits `\f` (PDF pages joined with `\n\n`). Running headers/footers — a top real‑world artifact — are never stripped, despite `docs/clean-text-review.md:18` claiming otherwise. **Verified via repo‑wide grep.**
- **High — English‑only:** every structural signal is hardcoded English (`EXPLICIT_CHAPTER_RE`, `SPEECH_VERBS`, `HONORIFIC`/`NAME_TOKEN` require `[A-Z]…`, `SENTENCE_RE` = `.!?` only, `tesseract -l eng`). Non‑Latin manuscripts degrade silently to one unresolved chapter with oversized, speaker‑less segments.
- **High — locked‑segment misplacement:** on offset drift after edits/reparse, the lock fallback compares *old* offsets against *new* scene offsets in different coordinate systems (`repository.py:463-478`) — a lock can silently land in the wrong scene, untested beyond the no‑edit case.
- **High — unbounded segment size:** `_split_narration_group` never splits inside a sentence (`structure_parsing.py:1369-1389`); a run‑on/OCR‑garbled passage yields a segment far over `max_chars` with only an info flag (and the "long" threshold is hardcoded `900`, decoupled from the configurable 120–2000 range).
- **Medium:** `structure_parsing.py` is a 1637‑line God object threading a mutable `warnings` list through every pass; sequential per‑batch LLM round‑trips (180s each) could take tens of minutes on a novel; cast mention‑evidence scan is O(candidates × segments) with no cached index; OCR confidence is a fixed `0.75` constant discarding Tesseract's real signal; duplicate legacy/v2 PDF paths with different heuristics; scattered magic thresholds (`0.72`, `0.8`) and batch sizes duplicated across three files.
- **Low:** two independently‑maintained stop‑word lists (`structure_parsing.py` vs `cast_discovery.py`); `_merge_broken_line_wraps` corrupts poetry/script formatting; manifest read swallows `JSONDecodeError` → `{}`.

**Historical product‑lens gaps (cast/speaker recall, 2026-07-03).** Without Ollama, narration‑only characters never enter the Bible (deterministic candidates come only from segments that already carry a `speaker_candidate`); nickname/diminutive coreference ("Elizabeth"/"Liz") isn't linked; merge verification isn't batched (context overflow → silent `{}`); ambiguous 2‑person exchanges are *detected* but never resolved (no turn‑taking or pronoun coreference), so common dialogue lands in review; multi‑paragraph quotes are demoted to narration (`structure_parsing.py:1163-1186`); chapter detection misses numeric‑only / centered / roman‑numeral headings.

**Recommendations.** Fix or delete the header/footer cleaner + add an integration test **(S)**; hard‑cap segment split with a clause‑level fallback **(S)**; make sentence terminators + OCR language configurable and warn on non‑Latin **(M)**; store a content fingerprint with locks to detect drift → review issue **(M)**; split `structure_parsing.py` along its passes, converting `warnings` to return values **(L)**; parallelize/pipeline + persist partial LLM progress **(M)**; add deterministic mention‑based candidates + fuzzy nickname matching + turn‑taking resolver **(M each)**; centralize thresholds/constants **(S)**; surface real OCR confidence **(S)**.

### 5.3 Voice, TTS, rendering & assembly

**Strengths.** Clean provider ABC with **no hidden cloud fallback anywhere**; content‑addressed render caching with a real parent‑chain history and field‑level diffing; assembly fails closed on missing renders rather than padding silence; sound design is a genuine explicit opt‑in with per‑type gain ceilings + ducking; `ManagedKokoroSetupService` is well engineered (isolated venv, atomic tmp→`.replace()` downloads, self‑validating synthesis probe, persisted state); `TtsSettingsStore.save()` re‑validates readiness so a broken config can't become active; direction resolution precedence (override → SegmentDirection → project default → neutral) matches the docs and locks are protected at the DB `upsert`.

**Issues.**
- **Critical — direction no‑ops** (see finding #2).
- **High — no exception handling on `generate_segment`/`preview_voice`** (`main.py:1197-1207`): the routine not‑found `ValueError`, `subprocess.TimeoutExpired`, and `OSError` all surface as raw 500s; `_run_tts_command` doesn't catch `TimeoutExpired`, `_validate_wav` only catches `wave.Error` (a missing output file → uncaught `FileNotFoundError`).
- **High — incomplete fingerprint** (see finding #7).
- **Medium — render race:** `render()` opens three separate sessions around a multi‑minute `preview()` with no lock and no `(segment_id, render_key)` uniqueness — concurrent requests double‑synthesize and fork history; `_tip()` then tie‑breaks on unordered iteration.
- **Medium — mutable adapter singleton:** `container.tts_adapter` is swapped in place (`main.py:291,340`); a settings change mid‑production leaves the job on a stale adapter while `status()` reports the new identity → just‑rendered segments look instantly stale.
- **Medium — whole‑chapter in‑memory pure‑Python DSP** (`assembly.py:300-441`, `review.py:136-160`) run inline inside a `202`‑labeled but actually blocking `assemble_chapter` endpoint.
- **Medium — subprocess gaps:** long segment text passed as argv (argv‑length limits) for Kokoro/XTTS (Piper uses stdin); timeout kills only the direct child, not grandchildren (espeak/phonemizer orphans); no process‑group management.
- **Low:** dead fields `SegmentRenderRequest.output_format` (fragments the cache when toggled) and `DirectionProfile.no_sfx`; placeholder `peak`/`waveform`/`silenceRanges` presented as real; Kokoro branch of `_normalized` leaves stale piper/xtts fields; mock TTS ignores voice/direction so it can't validate direction end‑to‑end.

**Historical product‑lens gaps (audio quality, 2026-07-03).** 16 kHz mono ceiling (#3); no loudness normalization / LUFS target, raw‑level mix with hard clip (`assembly.py:461`); `pauseAfterMs`/`pauseBeforeMs` ignored at assembly (fixed 350/800 ms); ambience loops without crossfade (audible seams); **XTTS reloads the multi‑GB model via a fresh `python -c` per segment** (`tts_providers.py:384-400`) — effectively unusable per chapter; all backends spawn a subprocess per segment (serial).

**Recommendations.** Wire pace/style to engines or shrink the advertised support **(M)**; honor per‑segment pauses in assembly **(M)**; add the sibling `except ValueError` + catch `TimeoutExpired`/`OSError` **(S)**; complete the fingerprint incl. `language` **(M)**; add `(segment_id, render_key)` unique constraint + deterministic `_tip` **(S)**; replace the mutable adapter field with a `resolve_tts_adapter()` accessor **(S)**; rewrite the PCM path with numpy/audioop + streaming + 44.1 kHz + loudness normalization **(L)**; persistent local TTS worker (load model once, stream segments, stdin for long text) **(M)**; remove/exclude dead fields from the fingerprint **(S)**; populate or null the audio metadata **(M)**.

### 5.4 Readiness QA, review & export

**Strengths.** Genuinely immutable, append‑only render/patch model with real lineage; `SegmentRenderer._tip()` correctly walks the parent chain to find the true tip (just not used everywhere); deterministic DB‑backed QA with dedupe keys; per‑output SHA‑256 embedded in the manifest *before* zipping (recipient can verify each file from the ZIP alone); atomic export publish via `.staging` → `Path.replace()`.

**Issues.**
- **Critical — random‑UUID "latest" selection** (finding #1), affecting assembly, export, readiness, patch‑lineage labeling, and export listing order.
- **High — issues never auto‑resolve + project‑wide export blocking** (finding #5): render‑id/check‑id dedupe means a fixed problem's `open` issue is never closed; export blocks on *any* project‑wide `open`+`blocking` issue, not the chapters being exported, so a single‑chapter export can be blocked by an unrelated chapter and a project can become permanently unexportable — or bad audio ships when a human clears the issue with no re‑validation.
- **Medium — export memory blowup:** `hashlib.sha256(target.read_bytes())` per chapter and `sha256(archive.read_bytes())` on the whole finished ZIP (`exporting.py:127,193`) load entire (multi‑GB) files into memory; the ZIP write itself streams fine.
- **Medium — no failure cleanup / no retention:** an ffmpeg failure mid‑export leaves `export_*.staging` dirs forever with no `try/finally` and no `status="failed"` record; there is no `DELETE /exports/{id}` so iterative patch→export cycles accumulate large ZIPs unbounded.
- **Medium — QA thinner than `docs/qa-rulebook.md`:** only a narrow technical layer exists; silence fires at 100% zero bytes only; no truncation heuristic; no chapter loudness/LUFS; export copies+checksums bytes without re‑decoding, so a disk‑full mid‑copy yields a "successful" export with a valid checksum of truncated data.
- **Low:** per‑sample Python scans on every `qa_chapter` (fires after every one‑line patch); inconsistent duration‑mismatch tolerance (`readiness` 100 ms vs `review` 50 ms); readiness score isn't severity‑weighted (can show "95% ready" while export‑blocked); unreachable `elif has_chapters` branch (`readiness.py:558`); `inspector()` N+1 comments + duplicate render‑chain fetches.

**Recommendations.** Add `created_at` + repoint latest queries (or reuse `_tip`) and assert `revision` match in `_resolve_inputs` **(M)**; auto‑close superseded issues + scope blockers to requested chapters **(M)**; chunked hashing **(S)**; `try/finally` staging cleanup + failed‑export record + delete/retention **(S/M)**; post‑copy WAV/MP3 re‑validation before checksum **(S)**; coarse loudness + truncation heuristics **(M)**; unify tolerance constant + severity‑weighted score **(S)**.

### 5.5 Data layer (DB, migrations, domain models)

**Strengths.** Deliberate, consistent metadata/blob split (paths only, no blobs in SQLite); data‑mapper schema with hand‑written joins (no lazy‑load surprises); genuine append‑only history with `parent_render_id` linking; user‑lock columns threaded consistently and respected; **batched (non‑N+1) hot‑path reads** in production (`production.py:109-113,161-165` fetch overrides/voices/directions for all segment ids up front); defensive `delete_voice` in‑use guard compensating for absent FK cascades; idempotent issue creation via `dedupe_key`; clean linear migrations with working `downgrade()`.

**Issues.**
- **High (S1) — SQLite concurrency unmitigated** (finding #4): `check_same_thread=False` but no WAL, no `busy_timeout`, no retry, while raw job threads write concurrently with request threads — `database is locked` likely *today*, not just at scale.
- **High (S2) — two schema‑evolution mechanisms** (Alembic vs `_repair_sqlite_schema_drift`) with no shared source of truth and no CI diff; a forgotten repair entry crashes real users on old DBs but passes all tests.
- **High (S3) — foreign keys not enforced** (`PRAGMA foreign_keys` off, no `ondelete=`); orphan rows accepted; only mitigated by the current absence of delete endpoints.
- **Medium (S4) — missing indexes** on several FK columns used in scans (`JobRecord.project_id`, `RenderQueueItemRecord.voice_profile_id`, `PatchAttemptRecord.*_render_id`, `SegmentProductionOverrideRecord.voice_profile_id`, `CharacterVoiceAssignmentRecord.voice_profile_id`, etc.).
- **Medium (S5) — docs drift:** concrete mismatches in `docs/db-schema.md`/`domain-model.md` (`voice_profiles` documents `base_voice_id`/`settings_json`/`is_narrator_default` that don't exist; `character_voice_assignments.project_id` and its unique constraint don't exist; `comments` documents `project_id`/`chapter_id`/`created_by` that don't exist; `issues.scene_id` doesn't exist).
- **Medium — minor N+1 in read‑models** (`review_workbench.inspector` per‑issue comment queries + duplicate render‑chain fetches; no `get_by_segment` for speaker attributions → pulls whole‑project list and filters in Python).
- **Low — session context manager** doesn't explicitly `rollback()` on exception (safe today via `close()`, latent trap); JSON‑blob columns preclude SQL filtering for a few app‑side‑filtered fields; manual Pydantic↔SQLAlchemy mapping with no drift detector; SQLite scale ceiling (`StructureRepository.replace()` loads all chapters/scenes/segments into memory per reparse) — a documented "Later: Postgres" concern.

**Recommendations.** Connect‑hook PRAGMAs (WAL + `busy_timeout` + `foreign_keys=ON`) + commit retry **(S)**; add `ondelete=` before any delete endpoint **(S)**; CI `alembic upgrade head` vs `Base.metadata` diff, and longer‑term make `create_schema()` run Alembic and retire the repair fn **(M→L)**; add the missing indexes **(S)**; regenerate schema docs + drift test **(S)**; batch/de‑dup the workbench queries + add `get_by_segment` **(S)**; explicit session rollback **(S)**; ORM‑column ↔ domain‑field parity test **(M)**.

### 5.6 Frontend dashboard (Next.js)

**Strengths.** Genuinely good domain‑driven component decomposition (40 presentational components, pure props‑in/callbacks‑out); thoughtful workflow modeling — step status derived from real domain state, not a manual wizard index (`lib/workflow.ts`); consistent accessibility groundwork (`aria-current="step"`, `role="alert"`/`aria-live`, `:focus-visible`); **real E2E coverage** (`tests/foundations.spec.ts`, 685 lines, 7 scenarios) that boots the actual FastAPI backend via Playwright and drives full flows incl. a mocked Kokoro install and WAV‑export checksum assertions; `strict: true` TS; local‑first privacy reflected directly in the UX (rights consent, reference‑voice opt‑in).

**Issues.**
- **High — god component:** `project-dashboard.tsx` (403 LOC) has **66 `useState`** + ~50 async handlers; any keystroke re‑renders the whole tree; no `React.memo` anywhere, `useMemo`/`useCallback` in only 3 files.
- **High — single global `busy` boolean** gates unrelated actions (saving a character disables "Produce chapter").
- **High — single global error/notice slot** at page top is the only feedback surface for ~50 handlers; deep errors can be off‑screen and are overwritten by the next notice.
- **High — no runtime validation of API responses:** `request<T>()` casts `response.json()` to `T` with no zod/schema, while the backend hand‑builds camelCase dicts field‑by‑field — a renamed field fails silently as `undefined` deep in a component.
- **High — no list virtualization:** `SegmentList`/`StoryMapPanel` render every segment with a full editor card; the test validates scroll with only 24 segments — real chapters have hundreds/thousands.
- **Medium:** two incompatible job‑polling strategies (four `useEffect`+`setTimeout` chains vs a blocking `waitFor` loop with no progress feedback); duplicated `emptyTts`/`csvList` helpers; no unit‑test layer (no Vitest/RTL) so `workflow.ts`/`format.ts`/`api.ts` error handling and many secondary flows are untested; no dark mode; deep prop‑drilling of callbacks.
- **Low:** raw JSON evidence dumped in `<pre>` to end users; hardcoded `NEXT_PUBLIC_API_URL` fallback with no runtime reconfig.

**Recommendations.** Split dashboard state into domain hooks (`useProjectState`, `useVoiceState`, …) **(M)**; per‑action loading state **(S–M)**; one reusable `useJobPolling` hook replacing both patterns **(M)**; a fetch/cache layer (TanStack Query) **(M–L)**; runtime response validation via zod or `openapi-typescript` codegen from the API schema **(M)**; virtualize segment lists **(S–M)**; scoped/toast error surface **(S)**; de‑dup helpers **(S)**; add Vitest+RTL unit tests **(M)**; `prefers-color-scheme` **(S)**.

### 5.7 Local AI, tooling, config & tests

**Strengths.** Security‑conscious subprocess handling (no `shell=True`, `check=False` + explicit capture, per‑job timestamped logs); privilege awareness (Linux `sudo -n`, Windows `--accept-*`); fail‑closed LLM with no cloud fallback + bounded retry; strong test isolation (`tmp_path`, `monkeypatch`, mocked subprocess/Ollama); YAML‑driven catalog with typed entries; comprehensive health checks; platform‑aware PATH resolution. **87 tests across 15 API test files** plus the frontend E2E — solid for the API surface. `mypy --strict` and `ruff` configured.

**Issues.**
- **High — no CI/CD** (corroborated across analyses).
- **High — long unbounded install timeouts** (1800s tools / 7200s Ollama) with no heartbeat or cancel endpoint; a long download blocks the job queue.
- **High — Ollama client has a 2s timeout and no retry/backoff** (`local_llm.py`, `local_ai/service.py:417-422`); a transient blip fails all extraction with a generic message.
- **High — fragile winget "already installed" detection** via lowercased substring matching (`service.py:49-55`) — locale/version differences bypass it.
- **Medium:** install logs grow unbounded (no retention); catalog not validated on startup (malformed YAML only fails when a specific model is requested); LLM extraction silently truncates source at 12 KB (`local_llm.py:152`) with no warning — misses characters/events past 12 KB; version parsing takes the first stdout line blindly; uninstall path has zero test coverage; Ollama health check doesn't verify model integrity (no test inference).
- **Correction to note:** a sub‑analysis flagged "no lock file," but **`uv.lock` does exist at the repo root** — the real gap is that it isn't *enforced* in CI (which is genuinely absent). Direct deps still use `>=` in `pyproject.toml`.

**Recommendations.** Add GitHub Actions running `pytest`/`ruff`/`mypy`/`web:lint`/`web:typecheck`/Playwright **(M)**; install‑job heartbeat + cancel endpoint **(M)**; Ollama retry+backoff and a larger timeout **(S)**; robust winget detection via exit code + regex **(S)**; log retention **(S)**; startup catalog validation **(S)**; warn on LLM truncation + raise the window or chunk **(S)**; uninstall tests **(S)**; optional Ollama test‑inference integrity check **(M)**.

---

## 6. Overall flow & operation assessment

**What works well as a system.** The stage contract is real: each stage persists durable artifacts + a manifest, downstream invalidation anchors on the segment, and the human‑in‑the‑loop review layer is honest (every candidate/warning carries offsets, rule names, and previews). The readiness gate is the right backbone — layered text → structure → speaker → voice → direction → audio → export checks that block on genuine problems. Fail‑closed local providers and LLM‑optional parsing mean the product degrades gracefully instead of hallucinating or silently going to the cloud. These are the hard things to get right, and they *are* right.

**Completion update.** The original operational failure mode was a disconnect between computed state and delivered artifact. Phase 0-4 closed that loop: assembly/export now use deterministic current renders, patching forces fresh audio with resolved voice/direction, direction reaches supported audio paths, readiness re-derives live state, and transcript/export/approval workflows deep-link back to the exact artifact needing attention.

**Scale & performance.** The operation is built for one book at a time on one machine, which is the stated scope — but three things will bite before "scale": pure‑Python per‑sample DSP (minutes per assemble/QA), whole‑file in‑memory hashing at export, and unbounded thread‑per‑job over unhardened SQLite. The first two are localized rewrites; the third is a small hardening pass plus a bounded executor.

**Governance/DevEx.** The completed workflow now treats validation, schema drift, and documentation updates as part of done. Further DevEx work can still improve router modularity, generated client contracts, frontend state decomposition, and long-run performance.

---

## 7. Consolidated roadmap completion

**Phase 0 — Trust foundation:** render/export ordering, patch rerender correctness, live readiness, SQLite/worker hardening, and CI/schema drift guard completed.

**Phase 1 — Honesty and compounding loop:** direction transmission, correction propagation, evidence triage queues, and container-derived structure signals completed.

**Phase 2 — Publishable audio:** mastered audio baseline, real audio QA, and export polish including M4B/MP3 metadata/retail samples completed.

**Phase 3 — Algorithmic depth:** character disambiguation, speaker attribution, casting traits/auditions, persistent local TTS worker, ASR verification, evidence-based direction inference, and structure depth completed.

**Phase 4 — Workflow experience:** transcript review, scoped issues/export blockers, ranked readiness worklist, unified next-best action, and listened chapter approval completed.

---

## 8. Notes on method & confidence

- Findings marked **verified** were confirmed directly against source in the 2026-07-03 session and many were then remediated by the completed roadmap.
- The SQLite‑concurrency and CI‑absence findings were reached **independently** by more than one analysis, which raised confidence and drove Phase 0 hardening.
- One sub‑analysis's "no lock file" claim was **corrected** here: `uv.lock` exists at the repo root.
- File:line references reflect the state of `main` at analysis time and must be spot‑checked before acting on any historical issue, as the codebase has changed substantially.
