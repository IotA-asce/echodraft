# Echodraft — Deep Analysis & Improvement Report

**Date:** 2026-07-03
**Scope:** Full system — FastAPI backend (~11.3k LOC Python), Next.js dashboard (~3.5k LOC TS/TSX), SQLAlchemy/SQLite data layer, local‑AI/model‑center tooling, and the end‑to‑end production pipeline.
**Method:** The codebase was mapped, then analyzed in parallel across seven subsystems by focused sub‑agents (code‑structure lens and product‑quality lens), with the highest‑impact findings independently verified against source. File:line references throughout point to specific evidence.

> **Corpus:** `apps/api/src/echodraft_api` (27 modules; `main.py` 1685 LOC, `structure_parsing.py` 1637 LOC), `apps/web/app` (40+ components), `libs/db` (45 tables, 22 migrations), `libs/domain-models` (~100 Pydantic models). No import cycles. Services under `services/` are empty placeholders.

---

## 1. Executive summary

Echodraft is an unusually **well‑architected alpha**. The core design ideas — segment‑as‑atomic‑unit, append‑only render history, manifest‑driven stages, evidence‑first review, deterministic‑with‑optional‑LLM parsing, and strict fail‑closed local providers — are coherent, consistently applied, and genuinely differentiated from one‑shot TTS tools. Domain logic is cleanly separated into per‑concern service modules, the DI container is simple, and the documentation set is extensive.

The gap between the current state and "produces a flawless, publishable audiobook" comes down to a handful of **correctness bugs** and **quality ceilings** that are individually fixable but currently invisible because they hide behind green "ready" signals:

1. **Patched audio can silently fail to reach the export** — "latest render" is selected by lexicographically sorting a *random* UUID, not by time. *(Critical, verified)*
2. **Direction Studio does nothing audible for 3 of 4 real TTS providers** — pace/style/pause are advertised, echoed back in the API, but never transmitted to the engine. *(Critical, verified)*
3. **Final audio is permanently capped at 16 kHz mono** — telephone‑grade, below the 44.1 kHz audiobook standard, regardless of how good the source voice is. *(High)*
4. **Concurrency is unsafe** — unbounded thread‑per‑job over a SQLite database with no WAL mode, no `busy_timeout`, and no `(segment_id, render_key)` uniqueness, so real use will hit `database is locked` errors and forked render history. *(High, corroborated by two independent analyses)*
5. **QA is thinner than documented** — audio QA metrics are stubbed (`peak:0`, `waveform:[]`), silence detection only fires on 100%‑zero files, and QA issues never auto‑resolve, so a project can become permanently unexportable or export bad audio via a manual status change. *(High)*

None of these require re‑architecting. The strong bones are already in place; the work is closing the loop between what the pipeline *computes* and what it *delivers*.

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
  → Readiness QA → Review & patch (fix one line, re-render, reassemble) → Export WAV/MP3 ZIP (manifest + lineage + checksums)
```

**Composition.** `create_app()` (`main.py`) builds a single `AppContainer` dataclass (`container.py:54-82`) holding one instance of every repository plus the artifact store, TTS settings/adapter, and an in‑process job runner. There is **no `Depends()`‑based DI** — every route reads `request.app.state.container` directly (~80 call sites) and constructs a fresh stateless service (`IngestionService(container)`, `SegmentRenderer(container)`, …) per request. Long work is submitted to `InProcessJobRunner`, which spawns a **daemon `threading.Thread` per job** and returns `202`; clients poll `GET /api/v1/jobs/{id}`.

**Storage split (a real strength).** SQLite holds only metadata and path strings; all audio/manifests/waveforms live on the filesystem in a per‑project tree. Render history is genuinely append‑only (`SegmentRenderRecord` never updated; new rows link via `parent_render_id`). The single artifact read gateway (`get_artifact`, `main.py:455-464`) correctly containment‑checks resolved paths, and upload endpoints strip filenames to `Path(...).name` — path‑traversal handling is done right.

**Operational posture.** Local‑first, single‑user, loopback‑bound by default. Jobs are honestly non‑durable: `reconcile_interrupted()` fails any job left `RUNNING` after a crash with guidance rather than pretending to resume (`repository.py:255-268`).

---

## 3. Cross‑cutting themes

These patterns recur across subsystems and are worth treating as programs of work rather than one‑off fixes:

| Theme | Where it shows up | Impact |
|---|---|---|
| **"Compute then discard"** | Direction pace/pause/style computed but not sent to engines (`tts_providers.py`, `assembly.py:246-255`); `pauseAfterMs`/`pauseBeforeMs` ignored in assembly; `outputFormat`, `DirectionProfile.no_sfx` dead fields | Features look done in the UI/API but have no runtime effect |
| **Ordering by random UUID** | `assembly.py:185,221`, `exporting.py:220,454`, `readiness.py:493`, `rendering.py:53` all `.order_by(<record>.id.desc())` on `uuid4().hex` ids | Non‑deterministic "latest" selection; the report's #1 correctness bug |
| **Green signal ≠ true state** | Readiness/status use the correct chain‑walk (`_tip`), but assembly/export select renders by the broken UUID sort and never cross‑check `revision`; QA issues never auto‑close | "Ready" can be reported while the exported audio is stale or QA‑failing |
| **Unbounded concurrency over unhardened SQLite** | Thread‑per‑job (`jobs.py:27-43`) + no WAL/`busy_timeout`/FK PRAGMA + no `(segment_id, render_key)` unique constraint | `database is locked`, forked render history, oversubscribed CPU/GPU |
| **Contract kept in sync by hand** | Hand‑built camelCase dicts in services ↔ hand‑written Pydantic aliases ↔ hand‑written TS types in `api.ts`; no runtime validation, no codegen | Silent `undefined` in UI when a field is renamed; drift with no detector |
| **English‑only, keyword heuristics** | Chapter/scene/sentence regexes, speech verbs, honorifics, `tesseract -l eng`, substring emotion inference | Non‑English or unconventional manuscripts degrade silently to one giant chapter / mislabeled direction |
| **Pure‑Python per‑sample audio DSP** | `assembly.py:300-441`, `review.py:136-160` iterate millions of samples in interpreted Python on every assemble/QA | Minutes‑long patch→listen loop, high RSS; will not scale to book length |
| **No CI / automated gate** | No `.github/workflows`; `AGENTS.md` prescribes manual verify only | Regressions, doc drift, and schema‑drift desync go undetected |
| **Docs drifted from code** | `docs/db-schema.md`, `docs/domain-model.md`, `docs/qa-rulebook.md`, `docs/clean-text-review.md` describe columns/rules that don't exist or aren't implemented | Misleads contributors and overstates capability |

---

## 4. Prioritized top findings (the short list)

Ranked by impact on "a correct, publishable audiobook," with rough effort (S ≈ hours, M ≈ 1–3 days, L ≈ week+).

| # | Severity | Finding | Fix | Effort |
|---|---|---|---|---|
| 1 | 🔴 Critical | **Patch may not reach export.** Latest render chosen by `order_by(id.desc())` on random `uuid4` ids (`SegmentRenderRecord`/`ChapterRenderRecord` have **no `created_at`**). After a patch, assembly (`assembly.py:221`) picks the old render ~50% of the time; `patch_segment` still reports success. Race under concurrent patches. **Verified in source.** | Add `created_at` to `segment_renders`/`chapter_renders`/`export_packages` (fits the existing `_repair_sqlite_schema_drift` idiom + a migration); repoint every "latest/active" query to it, or reuse the already‑correct `_tip()` chain‑walk everywhere. Also assert `render.revision == segment.revision` in `_resolve_inputs`. | M |
| 2 | 🔴 Critical | **Direction Studio is a no‑op for Kokoro & XTTS.** Both Kokoro adapters advertise `{"pace"}` and echo `effectiveDirection`, but no speed flag is sent and the managed wrapper hardcodes `speed=1.0` (`kokoro_setup.py:419`). XTTS advertises `{"stylePrompt"}` but the subprocess only ever gets `(text, speaker_wav, language, file)` (`tts_providers.py:384-399`). Only Piper honors its controls. Emotion inference itself is crude substring matching where common words like "now" → `urgent` (`direction.py:139-175`). | Actually transmit pace/style to the engines; replace keyword inference with LLM tagging (reuse the wired Ollama path); shrink `direction_support`/`effectiveDirection` to the truth until fixed so the UI stops overstating. | M |
| 3 | 🟠 High | **16 kHz mono quality ceiling.** `ChapterAssembler` hardcodes 16 kHz / mono / 16‑bit and downsamples every render (`assembly.py:52-54, 395-441`). Below ACX 44.1 kHz standard — deliverable is permanently telephone‑grade. | Make rate/channels project‑configurable, default 44.1 kHz; move DSP to numpy/audioop/ffmpeg (also fixes #7). | L |
| 4 | 🟠 High | **Unsafe concurrency over SQLite.** Unbounded thread‑per‑job (`jobs.py:27-43`); no WAL, no `busy_timeout`, no FK PRAGMA (`database.py`); no `(segment_id, render_key)` uniqueness so double‑submits fork history. Corroborated by backend + data‑layer analyses. | `event.listens_for(engine,"connect")` → `PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`; bound jobs with a `ThreadPoolExecutor`; add the unique constraint; commit‑retry on `OperationalError`. | S–M |
| 5 | 🟠 High | **QA weaker than documented; issues never auto‑resolve; export blocked project‑wide.** Audio metrics stubbed (`peak:0`,`waveform:[]`,`silenceRanges:[[0,dur]]`, `rendering.py:76-79`); silence only fires at 100% zero bytes (`review.py:158`); no loudness/truncation checks (`docs/qa-rulebook.md` promises them). QA/readiness issues dedupe by render‑id/check‑id and never transition to resolved, so a fixed problem stays `open` and blocks export forever — or a human clears a blocking issue with no re‑validation and ships bad audio. | Compute real peak/RMS/LUFS/silence; auto‑close superseded issues on clean re‑render; scope export‑blocker query to the chapters actually being exported. | M |
| 6 | 🟠 High | **No CI and no schema‑drift guard.** `.github/workflows` absent; Alembic migrations and `_repair_sqlite_schema_drift` encode the same columns twice with no shared source of truth or check. | Add CI (`pytest`/`ruff`/`mypy`/`web:lint`/`web:typecheck`/Playwright); add a test that runs `alembic upgrade head` on a scratch DB and diffs against `Base.metadata`. | M |
| 7 | 🟠 High | **Render fingerprint incomplete.** Piper hashes only `model_path` not `config_path`; Kokoro hashes only the `.onnx`, not voices/executable; XTTS `model_version()` is a constant and **`language` is never in the fingerprint** — swapping the reference WAV in place or changing language serves a stale cached render (`tts_providers.py:285-363`). Contradicts `docs/tts-production-upgrade.md`. | Hash all files/config that affect output; add `language` to `render_identity()`. | M |
| 8 | 🟡 Medium | **`main.py` is a 1685‑line, ~101‑route monolith** with no `APIRouter` split and ad‑hoc `ValueError`/`KeyError`→status mapping (fragile string‑matching at `main.py:1069-1073`); `generate_segment`/`preview_voice` have **no exception handling** (raw 500s on the routine not‑found case and on TTS timeouts). | Split into `routers/*`, add a `get_container` dependency, register global exception handlers with one documented mapping. | L |

---

## 5. Subsystem deep analysis

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

**Product‑lens gaps (cast/speaker recall).** Without Ollama, narration‑only characters never enter the Bible (deterministic candidates come only from segments that already carry a `speaker_candidate`); nickname/diminutive coreference ("Elizabeth"/"Liz") isn't linked; merge verification isn't batched (context overflow → silent `{}`); ambiguous 2‑person exchanges are *detected* but never resolved (no turn‑taking or pronoun coreference), so common dialogue lands in review; multi‑paragraph quotes are demoted to narration (`structure_parsing.py:1163-1186`); chapter detection misses numeric‑only / centered / roman‑numeral headings.

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

**Product‑lens (audio quality).** 16 kHz mono ceiling (#3); no loudness normalization / LUFS target, raw‑level mix with hard clip (`assembly.py:461`); `pauseAfterMs`/`pauseBeforeMs` ignored at assembly (fixed 350/800 ms); ambience loops without crossfade (audible seams); **XTTS reloads the multi‑GB model via a fresh `python -c` per segment** (`tts_providers.py:384-400`) — effectively unusable per chapter; all backends spawn a subprocess per segment (serial).

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

**Where the operation breaks down.** The recurring failure mode is a **disconnect between computed state and delivered artifact**, and it clusters at the two "join" points of the pipeline:

1. **Segment → chapter (assembly).** The system computes the correct current render (`_tip`) for *status* but selects renders for *assembly/export* by random‑UUID sort and never checks `revision`. So the readiness gate and the actual bytes on disk can disagree. This is the single most important operational fix — it undermines trust in the entire patch loop, which is the product's headline feature.
2. **Direction → synthesis.** Direction is inferred, stored, resolved with correct precedence, echoed in the API… and then dropped at the adapter for 3 of 4 providers. The workflow *looks* complete at every UI step but produces flat delivery.

**Scale & performance.** The operation is built for one book at a time on one machine, which is the stated scope — but three things will bite before "scale": pure‑Python per‑sample DSP (minutes per assemble/QA), whole‑file in‑memory hashing at export, and unbounded thread‑per‑job over unhardened SQLite. The first two are localized rewrites; the third is a small hardening pass plus a bounded executor.

**Governance/DevEx.** For a project whose `AGENTS.md` prescribes a disciplined branch→verify→commit workflow and whose docs are this thorough, the **absence of CI is the highest‑leverage process gap** — it's what lets doc drift, schema‑drift desync, and the "compute‑then‑discard" regressions persist unnoticed. A modest CI matrix plus a schema‑drift test and a contract‑parity test would catch a large fraction of the findings above and prevent their recurrence.

---

## 7. Consolidated recommendation roadmap

**Phase 0 — Correctness & trust (do first; unblocks the value proposition).** Findings #1 (render ordering + revision assertion), #2 (direction actually reaches the engine, or honest capability), #5 (auto‑close issues + chapter‑scoped blockers + real silence/truncation checks), #4 partial (WAL/`busy_timeout`/FK PRAGMA + `(segment_id, render_key)` unique). Mostly S–M; the highest ROI in the report.

**Phase 1 — Quality ceiling & robustness.** #3 (44.1 kHz + numpy/ffmpeg DSP + loudness normalization), #7 (complete fingerprint incl. language), persistent TTS worker, export chunked hashing + failure cleanup + retention, LLM truncation/parallelism.

**Phase 2 — Maintainability & process.** #6 (CI + schema‑drift + contract‑parity tests), #8 (`main.py` → routers + global exception handling), split `structure_parsing.py`, frontend state‑hook decomposition + runtime response validation + `useJobPolling` + virtualization, regenerate drifted docs, centralize scattered thresholds.

**Phase 3 — Recall & polish.** Multilingual/broader chapter detection, multi‑paragraph quotes, speaker turn‑taking + coreference, nickname/fuzzy cast matching, mention‑based candidates, feedback loop that reuses human corrections, dark mode, pagination.

---

## 8. Notes on method & confidence

- Findings marked **verified** were confirmed directly against source in this session (render tables genuinely lack `created_at`; `.order_by(id.desc())` on `uuid4` ids at the cited call sites; direction not transmitted for Kokoro/XTTS; header/footer `\f` dead code; no `.github/workflows`; 101 routes in `main.py`).
- The SQLite‑concurrency and CI‑absence findings were reached **independently** by more than one analysis, which raises confidence.
- One sub‑analysis's "no lock file" claim was **corrected** here: `uv.lock` exists at the repo root.
- File:line references reflect the state of `main` at analysis time and should be spot‑checked before implementing, as the codebase is under active development.
