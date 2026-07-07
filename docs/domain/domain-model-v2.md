# Domain Model v2 — Consolidated Target Data Model

See also:
[domain-model.md](domain-model.md) (v1 / current state),
[db-schema.md](db-schema.md) (v1 physical schema),
[../architecture/target-architecture.md](../architecture/target-architecture.md),
[../architecture/extraction-pipeline-v2.md](../architecture/extraction-pipeline-v2.md),
[../pipeline/casting/automatic-casting-v2.md](../pipeline/casting/automatic-casting-v2.md),
[../pipeline/tts/tts-engine-strategy.md](../pipeline/tts/tts-engine-strategy.md),
[../pipeline/assembly/generative-sound-design.md](../pipeline/assembly/generative-sound-design.md),
[../pipeline/casting/voice-bible-spec.md](../pipeline/casting/voice-bible-spec.md),
[../architecture/pipeline-manifest-spec.md](../architecture/pipeline-manifest-spec.md)

## 1. Purpose, scope, principles

### Purpose

This document is the **single, consolidated target data model** for Echodraft v2.
Five sibling v2 docs each propose table and column changes in passing; this doc
reconciles all of them into one authoritative build contract so an implementer
never has to diff five documents (and their pseudocode JSON shapes) to learn what
the v2 schema actually is. Where two v2 docs propose overlapping or slightly
inconsistent storage, the reconciliation is stated **explicitly** and marked
**[RECONCILED]**.

This is a target/aspirational spec. It supersedes the data-model *deltas* scattered
across the v2 suite; it does **not** supersede [db-schema.md](db-schema.md) as the
description of the shipping schema until the migrations in §6 land.

### Scope (delta-oriented)

This doc is written as a **delta** against [domain-model.md](domain-model.md) and
[db-schema.md](db-schema.md), with the current SQLAlchemy models in
[`libs/db/src/echodraft_db/models.py`](../../libs/db/src/echodraft_db/models.py) as
ground truth (that file already contains several tables the v1 docs omit —
`segment_revisions`, `chapter_approvals`, `ambience_profiles`,
`project_production_settings`, `segment_production_overrides`, `segment_directions`,
`character_mentions`, `cast_graph_decisions`, `cast_merge_decisions` — all of which
are treated here as the real v1 baseline).

**What changes (covered in full in §3):**

| Area | New tables | Altered tables |
|---|---|---|
| Orchestration | `job_checkpoints`, `inference_cache`, `job_events` | `jobs` |
| Extraction v2 | `review_tasks` | `issues`, `speaker_attributions`, `chapters`, `scenes`, `segments`, `character_mentions`, `cast_graph_decisions` |
| Casting v2 | `voice_catalog_entries`, `casting_decisions` | `voice_profiles`, `character_voice_assignments`, `project_production_settings` |
| TTS v2 | `tts_engine_models` | `voice_catalog_entries` (identity/acting-refs), `segment_renders` (no schema change; see §3.4) |
| Sound design v2 | (none — reuses `inference_cache` for generated audio) | `scenes`, `ambience_assets`, `ambience_cues`, `project_production_settings` |
| Voice bible | `voice_bibles` | — |
| Series continuity (deferred) | `series_character_voice_links` | `projects` |

**What is unchanged.** Every other table keeps its v1 shape exactly:
`projects` (except the deferred `series_id` in §3.7), `source_documents`,
`source_pages`, `ocr_runs`, `ocr_page_results`, `canonical_spans`, `cleaning_runs`,
`text_cleanliness_issues`, `structure_parser_warnings` (retained but demoted — see
§3.2), `structure_locks`, `segment_revisions`, `segment_renders` (see §3.4 note),
`render_queue_items`, `chapter_renders`, `chapter_approvals`, `ambience_profiles`,
`readiness_reports`, `comments`, `patch_attempts`, `export_packages`, `characters`,
`pronunciation_entries`, `model_installations`, `model_install_jobs`, `llm_runs`,
`rights_declarations`, `cast_merge_decisions`. The core hierarchy
(`Project → Chapter → Scene → Segment`) and all its lifecycle states are unchanged.

### Principles (inviolable — every entity below obeys these)

1. **SQLite holds metadata only.** No audio, no manuscript text blobs, no model
   weights in the relational DB.
2. **No audio blobs in the DB, ever.** Audio artifacts (segment WAVs, chapter mixes,
   audition clips, acting-ref clips, generated ambience) live on the filesystem; the
   DB stores **paths only**. This is the single hardest constraint and it drives
   several storage decisions below (notably embeddings — §3.3).
3. **Append-only render/decision history.** `segment_renders`, `chapter_renders`,
   `casting_decisions`, `ambience_assets` (on regenerate), and `job_events` are
   append-only. Supersession is expressed with a pointer (`parent_render_id`,
   `superseded_by_id`), never an in-place overwrite or delete.
4. **The segment stays the atomic editable/renderable unit.** v2 adds finer
   *work units* (page, chunk, scene-window, cluster, cue) for orchestration, but the
   durable editable/renderable entity remains the segment. Work units are checkpoint
   rows keyed by content hash, not new first-class domain entities.
5. **Manifest-driven.** Every stage still emits a durable JSON manifest on the
   filesystem; the DB mirrors only what must be queried/joined (§5).

## 2. Entity overview (v2 ER map)

```text
                                   ┌─────────────┐
                                   │  projects   │◄──────────────┐ (series_id, deferred §3.7)
                                   └──────┬──────┘               │
        ┌───────────────┬────────────────┼──────────────┬───────┴──────────┐
        ▼               ▼                 ▼              ▼                  ▼
  source_documents   chapters        characters     voice_profiles   project_production_settings
   │  │  │  │          │                 │  │           │                  │ (narrator_casting_decision_id,
   │  │  │  └ canonical_spans           scenes│         │                  │  casting_style_preset,
   │  │  └ ocr_runs─ocr_page_results     │    │         │                  │  auto_cast_enabled,
   │  └ source_pages                    segments        │                  │  auto_sound_design_json)
   └ cleaning_runs / text_cleanliness   │  │  │  │       │                  │
                                        │  │  │  └ segment_directions       ▼
   ORCHESTRATION (per project/job)      │  │  └ segment_production_overrides│
   ┌──────────────────────────────┐    │  └ segment_revisions              voice_bibles ─(bible_json)
   │ jobs ─┬─ job_checkpoints      │    └ segment_renders ─ patch_attempts
   │       ├─ job_events           │
   │       └─ render_queue_items   │    CAST GRAPH & ATTRIBUTION
   │ inference_cache (kind=        │    ┌───────────────────────────────────────────┐
   │   llm|tts|audiogen|embedding) │    │ character_mentions ─► cast_graph_decisions │
   └──────────────────────────────┘    │ cast_merge_decisions                        │
                                        │ speaker_attributions (1:1 segment;          │
   EXTRACTION REVIEW                    │   + auto_accepted, decision_tier)           │
   ┌──────────────────────────┐        └───────────────────────────────────────────┘
   │ review_tasks ─◄ issues    │
   │ structure_parser_warnings │        CASTING v2                    TTS v2
   │   (demoted, retained)     │        ┌────────────────────────┐   ┌────────────────────┐
   │ readiness_reports         │        │ voice_catalog_entries  │   │ tts_engine_models  │
   └──────────────────────────┘        │  ▲   ▲          ▲       │   └─────────┬──────────┘
                                        │  │   │          │       │             │ (engine identity
   SOUND DESIGN v2                      │  │   │          └───────┼─ voice_profiles.voice_    ◄┘  referenced by
   ┌──────────────────────────────┐    │  │   │  casting_decisions│   catalog_entry_id            catalog entry)
   │ scenes.atmosphere_profile_json│───┐│  │   └──── character_voice_assignments
   │ ambience_assets (provenance)  │   ││  └──── series_character_voice_links (deferred §3.7)
   │ ambience_cues (origin,        │   │└────────────────────────┘
   │   evidence, muted, locked)    │   │
   │ ambience_profiles (unchanged) │   │  generated ambience WAV paths ─► inference_cache(kind=audiogen)
   └──────────────────────────────┘   └─ sound_plan_manifest.json (filesystem, not a table)

  EXPORT / RIGHTS (unchanged): export_packages, rights_declarations, chapter_approvals, comments
  MODEL CENTER (unchanged): model_installations, model_install_jobs, llm_runs
```

Legend: `─►` FK/reference, `─◄` one-to-many parent on the arrow-head side, `(…)` new columns.

## 3. Per-entity specs

Column type conventions match the existing codebase: `TEXT` (SQLAlchemy `String`/`Text`),
`INTEGER`, `REAL`, `BOOLEAN` (stored as SQLite integer), `DATETIME` (timezone-aware).
JSON is stored as `TEXT` with a `_json` suffix on the column name (existing convention:
`parser_evidence_json`, `evidence_json`, `metadata_json`). IDs are `TEXT` PKs
(`String(64)`), matching every existing table.

### 3.1 Orchestration

Motivated by [target-architecture.md](../architecture/target-architecture.md) §3–§6.
These make jobs a **checkpointed DAG of fan-out units** with a content-addressed
inference cache and a replayable event log.

#### `job_checkpoints` (new)

Durable per-unit completion record. Restart re-plans deterministically and skips units
whose checkpoint is `done` (target-architecture §3.4).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `unit_key` | TEXT | no | — | **PK.** `sha256(canonical_json({stage, stage_version, scope, inputs, model, params}))` (target-architecture §3.4). Content-addressed. |
| `job_id` | TEXT | no | — | FK → `jobs.id`. |
| `project_id` | TEXT | no | — | FK → `projects.id`. |
| `stage` | TEXT | no | — | e.g. `structure_map`, `cast_reconcile`, `speaker_attribution`, `segment_render`, `sound_plan`. |
| `stage_version` | TEXT | no | — | Algorithm version; bumping forces recompute (invalidates old `unit_key`s). |
| `scope_json` | TEXT | no | `{}` | `{chapterId, sceneId, windowId, …}`. |
| `status` | TEXT | no | `pending` | `pending`\|`running`\|`done`\|`failed`. |
| `attempt` | INTEGER | no | `0` | Retry counter (target-architecture §3.7). |
| `last_error` | TEXT | yes | — | Last failure message. |
| `output_ref` | TEXT | yes | — | Manifest/artifact **path** — never a blob. |
| `created_at` | DATETIME | no | now | |
| `updated_at` | DATETIME | no | now | |

- **Indexes:** PK(`unit_key`); `(job_id, stage, status)` for resume scans.
- **Invariants:** `unit_key` is globally unique and content-addressed, so an identical
  unit re-planned after restart maps to the same row (idempotent skip). A row is only
  `done` after `output_ref` is durable. Stage-level completion is a derived predicate
  (`all units of scope done`), not stored here (the orchestrator marks stage/scope done
  via a `job_events` row + the `jobs.stage_cursor`).

#### `inference_cache` (new) **[RECONCILED]**

Content-addressed cache in front of **every** inference call, so reruns are near-free.

**Reconciliation.** Three docs describe a cache:
(a) target-architecture §3.5 defines an `inference_cache` **table** with inline
`value_json` for small LLM outputs and `value_path` for large (TTS) outputs;
(b) extraction-pipeline-v2 says the LLM cache "lives on the filesystem … keyed
alongside the existing `llm_runs` artifacts";
(c) generative-sound-design defines a filesystem cache at
`.echodraft/cache/generated-audio/{key}/asset.wav` + sibling `metadata.json`, keyed by
`sha256(model_id|prompt|duration|seed|params_version)`.
These are unified into **one `inference_cache` table** that is a **filesystem index**:
the row holds the key and metadata; large values (`tts`, `audiogen`) always live on the
filesystem and the row stores `value_path`; small values (`llm`, `embedding`) may inline
in `value_json`. The generated-audio cache directory is simply the `value_path` store for
`kind = audiogen`; the LLM prompt/response artifacts remain co-located with `llm_runs`
and are pointed at by `value_path` for `kind = llm` when not inlined. There is exactly one
cache abstraction, not three.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `cache_key` | TEXT | no | — | **PK.** Inference-relevant subset of the unit key (target-architecture §3.5). For `audiogen` this is the sound-design key form. |
| `kind` | TEXT | no | — | `llm`\|`tts`\|`audiogen`\|`embedding`. |
| `model_id` | TEXT | no | — | e.g. `qwen3:4b`, `stable-audio-open-1.0`, `chatterbox`. |
| `model_version` | TEXT | yes | — | Pinned version/checksum tag. |
| `schema_id` | TEXT | yes | — | Prompt schema / task template id (LLM) or prompt-template version (audiogen). |
| `value_json` | TEXT | yes | — | Small **validated** output inline (LLM JSON, embedding vector as JSON array). |
| `value_path` | TEXT | yes | — | Filesystem path for large output (WAV). |
| `bytes` | INTEGER | no | `0` | Size for LRU accounting. |
| `hit_count` | INTEGER | no | `0` | |
| `created_at` | DATETIME | no | now | |
| `last_hit_at` | DATETIME | yes | — | |

- **Indexes:** PK(`cache_key`); `(kind, last_hit_at)` for LRU eviction sweeps;
  `(model_id, model_version)` for "clear cache for model X" on a model bump.
- **Invariants / rules:** Exactly one of `value_json` / `value_path` is set. **Audio is
  always `value_path`** (principle 2). LLM values are cached only **after** JSON-schema
  validation passes (fail-closed contract preserved). The cache is a *performance layer,
  never a source of truth*: deleting any row only costs recompute.
- **Retention / pruning (defined here, per the brief).** LRU by `bytes` with ceiling
  `ECHODRAFT_CACHE_MAX_GB` (default 5 GB). Eviction order within a sweep: lowest
  `last_hit_at` first; a row whose `unit_key` still has an in-flight `job_checkpoint`
  is never evicted. On eviction of a `value_path` row the file is GC'd in the same pass.
  A file under the shared audiogen cache dir is deletable only when **zero**
  `ambience_assets.cache_key` rows reference it (generative-sound-design's rule folded in).
  Cache scope is **cross-project** (shared model warmups); see Open Questions for the
  project-scoped alternative.

#### `job_events` (new)

Persisted event stream for SSE replay (target-architecture §3.6). Append-only.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `event_id` | INTEGER | no | autoincrement | **PK.** Monotonic cursor for `Last-Event-ID` replay. |
| `job_id` | TEXT | no | — | FK → `jobs.id`. |
| `project_id` | TEXT | no | — | FK → `projects.id`. |
| `type` | TEXT | no | — | `job.*`, `stage.*`, `unit.*`, `artifact.ready`, `issue.opened`, `issue.resolved` (full taxonomy in target-architecture §3.6). |
| `stage` | TEXT | yes | — | |
| `scope_json` | TEXT | no | `{}` | |
| `payload_json` | TEXT | no | `{}` | Versioned envelope payload (`schemaVersion` inside). |
| `ts` | DATETIME | no | now | |

- **Indexes:** PK(`event_id` AUTOINCREMENT); `(job_id, event_id)` for replay-from-cursor.
- **Invariants:** Append-only; `event_id` strictly increasing (SQLite AUTOINCREMENT
  guarantees monotonicity even across deletes).
- **Retention / pruning (defined here).** Events are **operational, not a source of
  truth** (all durable state is reconstructable from checkpoints + manifests). Prune by
  age and by job terminality: keep all events for non-terminal jobs; for terminal jobs
  (`succeeded`/`failed`/`canceled`) keep the last `ECHODRAFT_EVENTS_RETAIN_DAYS`
  (default 7) then delete, and always keep a compacted tail (the last N=200 events per
  job) so a late client can still render a job's outcome. Pruning runs as a low-priority
  maintenance unit; it never blocks a live job.

#### `jobs` (altered)

Adds resumability and cancellation (target-architecture §3.4, §3.7).

| New/changed column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `status` (widened enum) | TEXT | no | — | Add `RESUMABLE` and `CANCELED` to the existing set. On startup, `reconcile_interrupted` marks `RUNNING` → `RESUMABLE` (was `FAILED`). |
| `cancel_requested` | BOOLEAN | no | `false` | Cooperative cancel flag; pools check it between units. |
| `stage_cursor_json` | TEXT | yes | — | `{stage, scope}` currently active, for fast resume and progress summary. |

- No other job columns change. `payload_json`/`progress_json` are retained (the fan-out
  progress `{stages:[{id, done, total, failed, status}]}` is written into `progress_json`).

### 3.2 Extraction v2

Motivated by [extraction-pipeline-v2.md](../architecture/extraction-pipeline-v2.md)
(confidence & flag model, decision audit) and the atmosphere-adjacent scene metadata
in [generative-sound-design.md](../pipeline/assembly/generative-sound-design.md).

#### Evidence / confidence on structure & attribution entities (altered)

The three-tier decision policy (`auto-accept` / `auto-accept-with-audit` / `flag`)
needs a durable audit flag on every auto-decided row. Rather than a single monolithic
`decision_audit` table (which would fragment the per-entity append-only model), the
audit is expressed as **columns on the entities that already carry `confidence` +
`evidence`**:

- `chapters`, `scenes`, `segments` (all already have `confidence REAL` +
  `parser_evidence_json`): add
  - `auto_accepted` BOOLEAN NOT NULL DEFAULT `false`
  - `decision_tier` TEXT NULL — `high`\|`mid`\|`flag` (null on locked/manual rows).
- `speaker_attributions` (already has `evidence_json`, `confidence`, `status`,
  `user_locked`): add
  - `auto_accepted` BOOLEAN NOT NULL DEFAULT `false`
  - `decision_tier` TEXT NULL
  - `review_task_id` TEXT NULL — FK → `review_tasks.id`, set only when the row is a
    `flag`-tier member of a grouped task.
- `character_mentions` and `cast_graph_decisions` are unchanged structurally; they
  already store `confidence`, `evidence_*`, `llm_run_id`, `metadata_json` — the vote
  tally and candidate set from S3/S4 go into their existing `metadata_json`.

**Invariant:** a row with `decision_tier = flag` must belong to exactly one open
`review_tasks` row (via `review_task_id` or, for structure spans, via the task's
`member_refs_json`). A row with `user_locked = true` is never re-decided and keeps
`auto_accepted = false`.

**`structure_parser_warnings` is demoted, not dropped.** It is retained for backward
compatibility (v1 rows keep working) but the v2 pipeline **stops emitting the
per-segment firehose** (the 2,453 + 731 warnings). Its role shrinks to genuine
low-level parser diagnostics; user-facing review moves entirely to `review_tasks`
(extraction-pipeline-v2 migration step 7).

#### `review_tasks` (new) — the aggregation entity that replaces flag floods

The single most important extraction-v2 data change: grouped review tasks keyed by
cause, so a hard book produces `< 20` tasks instead of thousands of per-segment findings
(extraction-pipeline-v2 §Confidence & flag model).

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | no | — | PK. |
| `project_id` | TEXT | no | — | FK → `projects.id`. |
| `cause_key` | TEXT | no | — | Stable grouping key, e.g. `attribution_ambiguous:chap_012`, `cast_name_confirm`, `structure_unsegmentable:chap_003`. |
| `category` | TEXT | no | — | `cast`\|`attribution`\|`structure`\|`casting`\|`direction`\|`sound_design`. |
| `scope_type` | TEXT | no | — | `project`\|`chapter`\|`scene`\|`character`\|`span`. |
| `scope_id` | TEXT | yes | — | |
| `title` | TEXT | no | — | e.g. "Chapter 12: 4 dialogue turns ambiguous between Reyes and Okonkwo". |
| `member_count` | INTEGER | no | `0` | Number of underlying findings the task aggregates. |
| `member_refs_json` | TEXT | no | `[]` | References to member rows (segment ids, attribution ids, spans) + per-member evidence, so one action resolves the cluster and confirmations propagate. |
| `evidence_json` | TEXT | no | `{}` | Windows, candidates, votes, `llmRunId`s — the "show your work" payload. |
| `status` | TEXT | no | `open` | `open`\|`resolved`\|`dismissed`. |
| `created_at` | DATETIME | no | now | |
| `updated_at` | DATETIME | no | now | |

- **Indexes:** PK(`id`); **unique** `(project_id, cause_key)` (partial: `WHERE status = 'open'`)
  so re-running a stage folds new members into the existing open task instead of creating
  a duplicate; `(project_id, status)`.
- **Relationship to `issues`.** `issues` remains the durable QA/editorial finding table
  (render QA categories, export blockers) and is unchanged except for one addition:
  - `issues.review_task_id` TEXT NULL — FK → `review_tasks.id`, letting a render-QA issue
    optionally roll up under a grouped task. Extraction *review* flags live in
    `review_tasks`; render/export *QA* findings stay in `issues`. A `review_task` may
    aggregate `issues` rows (via `member_refs_json`) but is the parent, never the child.

#### `scenes.atmosphere_profile_json` (altered) **[RECONCILED]**

Generative-sound-design adds a per-scene atmosphere profile (location/time/weather/mood/
tension/explicit-sound-events). It states this is a sibling to `scenes.parser_evidence_json`.
**[RECONCILED]** with the manifest question: the profile is stored **both** as
`scenes.atmosphere_profile_json TEXT NOT NULL DEFAULT '{}'` (DB, for the planner's queries
and the "Why this sound?" UI) **and** mirrored into `structure_manifest.json`'s per-scene
payload (filesystem source of truth). The JSON carries its own `schemaVersion` (§4).

### 3.3 Casting v2

Motivated by [automatic-casting-v2.md](../pipeline/casting/automatic-casting-v2.md).

#### `voice_catalog_entries` (new) — measured voice catalog **[RECONCILED across casting + TTS + target-architecture]**

The core casting fix: stop guessing facets from Kokoro ID prefixes; store one row per
usable voice populated from the voice's **own audio** (measured acoustics + LLM labels +
speaker embedding).

**Reconciliation.** Three docs touch voice metadata:
(a) target-architecture §6.1 says `VoiceProfileRecord` "gains real metadata columns
(gender, age band, timbre, accent, energy)";
(b) automatic-casting-v2 puts the measured metadata in a new `voice_catalog_entries`
table and gives `voice_profiles` only a `voice_catalog_entry_id` FK;
(c) tts-engine-strategy puts a "voice identity record" (seed / embedding / reference WAV /
acting-refs / engine model version) "in the voice profile".
**These are reconciled to a single home: `voice_catalog_entries`.** The measured facets
and the synthesized/cloned identity are the *same concept* at different `synthesis_kind`s
(fixed vs parametric vs cloned), so they belong in one table. `voice_profiles` does **not**
grow gender/age/timbre columns (target-architecture (a) is satisfied *by reference* via the
FK, not by duplicating columns) and does **not** grow a parallel identity blob
(tts (c) is satisfied by the same FK). This keeps one source of truth for "what this voice
is and how to reproduce it", and keeps `voice_profiles` the thin project-local binding it
already is.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | no | — | PK, e.g. `vcat_kokoro_af_bella_v1`. |
| `project_id` | TEXT | yes | — | **Null for globally shared engine voices**; set for a user-supplied cloning reference (project-scoped). |
| `engine` | TEXT | no | — | `kokoro`\|`piper`\|`xtts`\|`chatterbox`\|… |
| `engine_version` | TEXT | no | — | e.g. `managed-onnx-v1`. |
| `engine_voice_id` | TEXT | yes | — | Native voice id (fixed engines); null for parametric. |
| `synthesis_kind` | TEXT | no | `fixed` | `fixed`\|`cloned`\|`parametric`. |
| `gender` | TEXT | yes | — | Categorical facet (matching constraint). |
| `age_range` | TEXT | yes | — | |
| `accent` | TEXT | yes | — | |
| `locale` | TEXT | yes | — | |
| `timbre_json` | TEXT | no | `[]` | Free-vocabulary descriptors (shared vocab with character `speaking_style_json`). |
| `energy_default` | TEXT | yes | — | |
| `pitch_median_hz` | REAL | yes | — | Measured (signal processing, no LLM). |
| `pitch_range_json` | TEXT | yes | — | `[p10, p90]`. |
| `jitter_percent` | REAL | yes | — | |
| `shimmer_percent` | REAL | yes | — | |
| `tempo_wpm` | REAL | yes | — | |
| `spectral_brightness` | REAL | yes | — | |
| `embedding_path` | TEXT | yes | — | Filesystem `.npy` path — **not a blob** (see decision below). |
| `sample_paths_json` | TEXT | no | `{}` | `{auditionWav, waveformPreviewPng}` — filesystem paths only. |
| `seed` | INTEGER | yes | — | Deterministic seed for `parametric`/seed-conditioned identities (tts §6.1). |
| `reference_audio_path` | TEXT | yes | — | Canonical identity clip for `cloned`/synth identity (path only). |
| `acting_refs_json` | TEXT | no | `{}` | Per-emotion acting-ref clip **paths** (`{angry:…, whisper:…}`) — tts §5.4/§6.1. |
| `engine_model_version` | TEXT | yes | — | Model version this identity is valid for; a change triggers re-validation, not silent reuse (tts §6.4). |
| `license_json` | TEXT | no | `{}` | `{source, type, commercialUse, attributionRequired, consentRecordId}`. |
| `consent_record_id` | TEXT | yes | — | Required non-null before a `cloned` voice is auto-cast-eligible. |
| `labeled_by_json` | TEXT | no | `{}` | `{method, model, llmRunId, humanReviewed}`. |
| `schema_version` | TEXT | no | — | JSON-payload schema version (§4). |
| `created_at` | DATETIME | no | now | |

- **Indexes:** PK(`id`); **unique** `(engine, engine_version, engine_voice_id)` where
  `engine_voice_id` is not null (idempotent audition upsert); `(project_id)`;
  `(engine, gender, age_range, accent)` for catalog filtering.
- **Invariants:** exactly the identity fields the chosen engine uses are populated
  (`method` in `labeled_by_json` records which). A `cloned` entry with null
  `consent_record_id` is never returned to auto-cast. Sample/embedding/reference/acting-ref
  columns are **paths only** (principle 2).

**Embedding storage decision (asked by the brief): filesystem path, not a DB blob.**
A speaker embedding is ~192 floats (≈0.75–1.5 KB), so the *no-audio-blob* rule (principle 2)
does not strictly forbid it — that rule is scoped to **audio**, and an embedding is a small
metadata vector, not audio. We still store it as an `.npy` **path** (`embedding_path`) for
three reasons: (1) it matches both source docs (casting-v2 `vectorPath`, tts `embedding.npy`)
so no reconciliation drift; (2) it keeps SQLite rows small and backups/WAL cheap, and lets
numpy `mmap` the vector directly for the distinctiveness inner loop; (3) it keeps a single,
consistent "binary → filesystem, path → DB" rule that is trivial to audit rather than a
per-size judgement call. **Permitted alternative (Open Question):** because distinctiveness
scoring loads *all* project voice embeddings on every casting run, if profiling shows path
I/O dominates, an inline `embedding_json` (JSON array) MAY be added as a query-side cache —
this is explicitly allowed by the JSON policy (§4, small + read-together) and does **not**
violate principle 2. It is deferred until measured.

#### `casting_decisions` (new) — append-only assignment evidence

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | no | — | PK. |
| `project_id` | TEXT | no | — | FK → `projects.id`. |
| `character_id` | TEXT | yes | — | FK → `characters.id`; **null for the narrator row**. |
| `role` | TEXT | no | — | `narrator`\|`character`. |
| `voice_catalog_entry_id` | TEXT | no | — | FK → `voice_catalog_entries.id`. |
| `prominence_class` | TEXT | yes | — | `major`\|`minor`\|`walk_on`. |
| `score` | REAL | no | `0` | Winning score. |
| `candidate_scores_json` | TEXT | no | `[]` | Top-3 candidates with component sub-scores, constraints applied, co-occurrence conflicts avoided/accepted. |
| `evidence_json` | TEXT | no | `{}` | Matched/missed facets, reasons. |
| `algorithm_version` | TEXT | no | — | Casting algorithm version (determinism). |
| `catalog_version` | TEXT | no | — | Catalog snapshot used (explains why a later rerun differs). |
| `user_locked` | BOOLEAN | no | `false` | |
| `locked_reason` | TEXT | yes | — | |
| `superseded_by_id` | TEXT | yes | — | Append-only supersession pointer → newer `casting_decisions.id`. |
| `created_at` | DATETIME | no | now | |

- **Indexes:** PK(`id`); `(project_id, role)`; **partial unique** on
  `(project_id, character_id)` `WHERE superseded_by_id IS NULL AND role = 'character'`
  (at most one *active* decision per character); a mirror partial-unique on
  `(project_id)` `WHERE superseded_by_id IS NULL AND role = 'narrator'` (one active
  narrator decision).
- **Invariants / rules:** append-only (a rerun inserts a new row and sets the prior row's
  `superseded_by_id`, never updates in place). `casting_decisions` is the source of truth
  for *why*; `character_voice_assignments` stays the thin "what the project currently uses"
  read path.

#### `character_voice_assignments` (altered)

Add (automatic-casting-v2 §Data model): `user_locked` BOOLEAN NOT NULL DEFAULT `false`,
`locked_reason` TEXT NULL, `casting_decision_id` TEXT NULL (FK → `casting_decisions.id`).
Keeps its existing `unique (character_id)`. A row with **null** `casting_decision_id` is a
pre-auto-cast hand assignment and is treated as `user_locked` on the first auto-cast run
(backfill, §6).

#### `voice_profiles` (altered)

Add `voice_catalog_entry_id` TEXT NULL (FK → `voice_catalog_entries.id`) so a project-local
voice binding points at real measured metadata instead of the regex `_voice_facets()` guess.
**No** gender/age/timbre columns are added here (see the reconciliation above). Voices with
no catalog entry yet fall back to `_voice_facets()` during rollout.

#### `project_production_settings` (altered — consolidated from casting + sound + bible)

This one table receives additions from **three** v2 docs; consolidated here:

| New column | Type | Null | Default | Motivated by |
|---|---|---|---|---|
| `narrator_casting_decision_id` | TEXT | yes | — | casting-v2 (replaces the bare `narrator_voice_profile_id` as the *reasoned* narrator pointer; the profile id is kept for the render read path). |
| `casting_style_preset` | TEXT | no | `warm_neutral` | casting-v2 narrator style preset. |
| `auto_cast_enabled` | BOOLEAN | no | `true` | casting-v2 (default true for new projects). |
| `auto_sound_design_json` | TEXT | yes | — | sound-design (`{enabled, tier, sfxBudget, allowOpeningMusic, allowPeakMusic}`). |
| `voice_bible_id` | TEXT | yes | — | FK → `voice_bibles.id` (§3.6). |

Existing `narrator_voice_profile_id` and `default_direction_json` are unchanged.

### 3.4 TTS v2

Motivated by [tts-engine-strategy.md](../pipeline/tts/tts-engine-strategy.md).

**Voice identity persistence (seed / embedding / reference WAV / acting-refs) is
reconciled into `voice_catalog_entries`** (§3.3) rather than a separate table or a
`voice_profiles` blob — see that reconciliation. The remaining TTS-specific data model
change is an engine/model registry.

#### `tts_engine_models` (new) — engine/model identity registry

The direction→engine contract and reproducibility (R13/R15) need durable, queryable
engine identity beyond what `model_installations` records (which is a Model Center
*install* snapshot). This table records the *capability contract* per engine model.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | no | — | PK, e.g. `chatterbox@0.3.1`. |
| `engine` | TEXT | no | — | `kokoro`\|`piper`\|`xtts`\|`chatterbox`\|`orpheus`\|… |
| `model_version` | TEXT | no | — | Pinned version/checksum. |
| `tier` | TEXT | no | — | `S`\|`A`\|`C` (expressive/standard/cloud). |
| `direction_support_json` | TEXT | no | `[]` | The **truthful** control set the engine actually honors (only populated after bake-off confirms each control). |
| `synthesis_kinds_json` | TEXT | no | `[]` | `["fixed"]` / `["cloned","parametric"]` supported. |
| `model_installation_id` | TEXT | yes | — | FK → `model_installations.id` (link to install/verify state). |
| `license_summary` | TEXT | yes | — | Mirrors catalog `license_summary` (e.g. XTTS CPML caveat). |
| `created_at` | DATETIME | no | now | |

- **Indexes:** PK(`id`); **unique** `(engine, model_version)`; `(tier)`.
- **Invariants:** `direction_support_json` is a truthful capability claim, never a
  hypothesis — a control appears only after §10 bake-off confirms it (the doc's
  truthfulness rule made durable). `render_identity()` (and thus the `render_key`)
  references `(engine, model_version)`; **device/worker-mode remain excluded** from the
  key so CPU-vs-GPU of the same model does not stale audio.

**`segment_renders` and `chapter_renders` are structurally unchanged.** Acting-ref clip
paths and the per-character voice identity live in `voice_catalog_entries`; the per-render
seed and provider identity already flow through the existing `request_json` /
`render_key`. New engines only ever *append* new `segment_renders` rows (append-only
history), and all existing Kokoro renders keep their keys and stay valid (tts §11 migration).

#### Acting-reference clips metadata

Stored as **paths** in `voice_catalog_entries.acting_refs_json`
(`{emotion → wav_path}`). Generation provenance (ASR-validated, seed) rides in the sibling
`inference_cache` row (`kind = tts`). No new table — acting refs are per-voice-identity, and
that identity already has a home.

### 3.5 Sound design v2

Motivated by [generative-sound-design.md](../pipeline/assembly/generative-sound-design.md).
Generated ambience audio is cached via `inference_cache` (`kind = audiogen`, §3.1); the
per-chapter `sound_plan_manifest.json` is a **filesystem manifest, not a table** (it records
planner *decisions*, which are auditable on disk and do not need to be queried relationally).

#### `ambience_assets` (altered) — generated-asset provenance

| New column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `provenance` (widened) | TEXT | no | `uploaded` | Existing column gains valid values `generated`\|`bank` (was `uploaded` only). |
| `model` | TEXT | yes | — | e.g. `stable-audio-open-1.0`. |
| `prompt` | TEXT | yes | — | Normalized prompt text or bank query. |
| `seed` | INTEGER | yes | — | |
| `cache_key` | TEXT | yes | — | Points into the shared `inference_cache`/generated-audio store; **indexed**. |
| `qa_status` | TEXT | no | `n/a` | `passed`\|`failed`\|`regenerated`\|`n/a`. |

`license_note` (existing) is populated from the Model Center catalog `license_summary` at
generation time so licence travels with the asset. `asset_path` may point straight at the
**shared** cache file (never a per-project copy); GC only when zero rows reference the path.
**Append-only on regenerate:** a regenerate inserts a *new* `ambience_assets` row (matching
append-only render history), it does not mutate the old one.

#### `ambience_cues` (altered) — auto-placement provenance

| New column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `origin` | TEXT | no | `user_created` | `user_created`\|`auto_generated`. |
| `evidence_json` | TEXT | no | `{}` | Placing rule name + atmosphere fields (ambience/music) or `sentenceEvidence` (SFX). |
| `muted` | BOOLEAN | no | `false` | Mute without delete (keeps evidence trail). |
| `user_locked` | BOOLEAN | no | `false` | Mirrors `SceneRecord.user_locked`; a re-run of the planner never overwrites a locked cue. |

`scenes.atmosphere_profile_json` addition is specified in §3.2. `ambience_profiles`
(existing) is unchanged.

### 3.6 Voice bible

Motivated by [voice-bible-spec.md](../pipeline/casting/voice-bible-spec.md), which is
currently *unimplemented* (aspirational fields only).

**Decision: which aspirational fields become real columns vs a JSON payload.** The voice
bible is a **project-level editorial document** read as a whole at build time; almost none
of its fields are filtered/joined/aggregated on. By the queryability rule (§4) that means
**one table with a versioned JSON payload**, not dozens of scalar columns:

#### `voice_bibles` (new)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | TEXT | no | — | PK. |
| `project_id` | TEXT | no | — | FK → `projects.id`; **unique** (one bible per project). |
| `narrator_voice_profile_id` | TEXT | yes | — | Promoted to a **real column** (it is joined to on the render path and must be a hard, queryable pointer) — FK → `voice_profiles.id`. |
| `max_expressiveness` | TEXT | no | `medium` | Promoted to a **real column**: the direction→engine compiler (tts §5.1) reads it to *cap* compiled magnitude on every segment render; keeping it a first-class, defaulted scalar makes that cap cheap and unambiguous. |
| `narration_restraint` | TEXT | no | `high` | Promoted (same rationale as above; narrator lines default to restraint). |
| `allow_whispering` | BOOLEAN | no | `true` | Promoted (machine-checked gate on `whisper` direction). |
| `allow_shouting` | BOOLEAN | no | `false` | Promoted (machine-checked gate). |
| `bible_json` | TEXT | no | `{}` | **Everything else** as versioned JSON: `toneKeywords`, `pacingDefault`, `energyDefault`, `warmth`, `clarity`, `accentNotes`, `stylePrompt`, `doNotOverdo`, per-character `vocalIdentity`/`deliveryDefaults`/`emotionalRange`/`speechQuirks`/`usageRules`, `doNotCross` rules, `pauseStyle`, `dialogueSeparationGoal`. These are read as a whole, never queried individually. |
| `schema_version` | TEXT | no | — | JSON payload version (§4). |
| `created_at` | DATETIME | no | now | |
| `updated_at` | DATETIME | no | now | |

Rationale for the split: the four global-rule scalars (`max_expressiveness`,
`narration_restraint`, `allow_whispering`, `allow_shouting`) plus the narrator pointer are
**machine-checked constraints read on the hot render path**, so they are real columns with
sane defaults; the rest is editorial prose read as a document, so it is JSON. The do-not-cross
rules are *enforced elsewhere as behavior* (casting-v2 turns each into a machine check —
reserved narrator voice, `repeat_voice_penalty`, `distinctiveness_penalty`), so they need no
dedicated columns here beyond the JSON record of intent. Pronunciation entries already have a
first-class table (`pronunciation_entries`) and are **not** duplicated into the bible.

### 3.7 Series / cross-book continuity (deferred, phase-2)

Motivated by automatic-casting-v2 §7; explicitly **deferred past the first milestone**,
included so the schema needs no breaking change later.

- `projects.series_id` TEXT NULL (indexed) — groups projects into a series.
- `series_character_voice_links` (new): `id` PK, `series_id` TEXT NOT NULL,
  `canonical_character_key` TEXT NOT NULL (name-normalized), `voice_catalog_entry_id` FK,
  `confirmed_by` TEXT, `created_at`. **Unique** `(series_id, canonical_character_key)`.
  A link feeds `series_continuity_bonus` as a *preference* (never a hard constraint) and is
  only created after explicit user confirmation (cross-project matches never auto-merge).

## 4. JSON-payload column policy

The codebase already leans on `_json` columns; v2 formalizes when that is correct.

**Rule of thumb — queryability decides.**

- Use a **real column** (or a child table) when the value is filtered, joined, aggregated,
  sorted, or uniqueness-constrained on — i.e. the DB engine needs to *see inside* it.
  Examples promoted for exactly this reason: `voice_catalog_entries.gender/accent/…`
  (matching constraints, catalog filtering), `casting_decisions.role`
  (partial-unique index), `review_tasks.cause_key` (dedup uniqueness),
  `ambience_assets.cache_key` (indexed lookup), the four voice-bible global-rule scalars
  (read on the render hot path).
- Use a **JSON payload column** when the value is opaque to the query layer — read/written
  as a whole, diagnostic, evidence, or config: `evidence_json`, `candidate_scores_json`,
  `member_refs_json`, `atmosphere_profile_json`, `bible_json`, `direction_support_json`,
  `scope_json`, `payload_json`, `pitch_range_json`. Never index into JSON with SQLite
  `json_extract` on a hot path — if you need to, that field should have been a column.
- A JSON column that grows an unbounded list of *first-class entities* (each needing its
  own lifecycle/lock/history) is a smell — promote it to a child table. This is why
  grouped review is a `review_tasks` table, not a `flags_json` blob on the project.

**Schema-versioning convention for JSON payloads.** Every JSON payload that is a durable
contract carries a top-level `schemaVersion` (semver string), mirroring the manifest
common envelope (`pipeline-manifest-spec.md` §Common envelope). Tables whose *entire* row
is a versioned document also expose a `schema_version` **column** (`voice_catalog_entries`,
`voice_bibles`) so a migration/reader can branch without parsing the blob. Readers must
tolerate unknown newer minor versions (additive) and refuse unknown major versions
(fail-closed). Bump the minor version for additive fields, the major version for a
breaking shape change; a major bump on a decision/identity payload also bumps the relevant
`stage_version` / `algorithm_version` so cached/checkpointed outputs recompute (§3.1).

## 5. Manifest ↔ DB division of responsibility

Extends [pipeline-manifest-spec.md](../architecture/pipeline-manifest-spec.md). Principle:
**the DB stores what must be queried/joined/locked; the filesystem manifest stores the full
durable stage output and all diagnostics; audio and large payloads are filesystem-only.**

| Data | DB (SQLite) | Manifest (filesystem JSON) | Audio/large artifact (filesystem) |
|---|---|---|---|
| Chapter/scene/segment structure | rows in `chapters`/`scenes`/`segments` (+`confidence`, `auto_accepted`, `decision_tier`) | `structure_manifest.json` (full parse, coverage, per-segment `llmRunId`, evidence) | — |
| Scene atmosphere profile | **mirrored** `scenes.atmosphere_profile_json` (for planner queries) | authoritative in `structure_manifest.json` per-scene payload | — |
| Cast / mentions / merges | `characters`, `character_mentions`, `cast_graph_decisions`, `cast_merge_decisions` | `casting_manifest.json` (`profiles[]`, `clusters` diagnostics, `provisional`, `reconciledFrom[]`) | — |
| Speaker attribution | 1 row/segment in `speaker_attributions` | `attribution_manifest.json` (per-row method, votes, window id) | — |
| Voice catalog / identity | `voice_catalog_entries` (facets, paths) | audition manifest per engine | audition WAV, embedding `.npy`, acting-ref WAVs |
| Casting decisions | `casting_decisions` (append-only, why) + `character_voice_assignments` (what) | `casting_manifest.json` (per-assignment evidence, `catalogVersion`, `algorithmVersion`) | — |
| Segment/chapter renders | `segment_renders`/`chapter_renders` (paths, keys, lineage) | `segment_render_manifest.json`, `chapter_assembly_manifest.json` | speech WAV, mixed WAV |
| Sound plan | `ambience_assets`/`ambience_cues` (materialized cues) | **DB-mirrored decisions** live authoritatively in `sound_plan_manifest.json` (planner decisions, skips, budgets) | generated ambience WAVs (shared cache) |
| Orchestration | `job_checkpoints` (unit status), `jobs` | `run_report_manifest.json` (timing, cache hit-rate, time-to-first-audio) | — |
| Events | `job_events` (replay cursor) | — (events are transient; report manifest is the durable summary) | — |
| Inference outputs | `inference_cache` **index** (key, kind, bytes, path) | LLM prompt/response artifacts co-located with `llm_runs` | cached WAVs |

**DB-only** (no manifest): `job_checkpoints`, `job_events`, `review_tasks`, `voice_bibles`,
`inference_cache`, `render_queue_items`, lock rows. **Manifest-only / manifest-authoritative**
(DB mirrors a subset): `sound_plan_manifest.json`, `run_report_manifest.json`, the full
diagnostic payloads of every stage manifest. **Filesystem-only, path-in-DB:** all audio,
embeddings, reference/acting-ref clips, cached generations (principle 2).

## 6. Migration sequencing

Alembic revisions continue from the current head (`0024_segment_render_uniqueness`).
Each batch is **additive, independently shippable, and backward compatible** — every new
column is nullable or defaulted, so v1 rows keep working with no backfill required to *read*
them. Ordered to align with the v2 workstream phases across the suite.

| Batch | Rev (indicative) | Tables | Aligns with |
|---|---|---|---|
| **A — Orchestration foundations** | 0025 | +`job_checkpoints`, +`inference_cache`, +`job_events`; alter `jobs` (`cancel_requested`, `stage_cursor_json`, widen `status`) | target-architecture migration steps 1–2 |
| **B — Extraction confidence & flags** | 0026 | +`review_tasks`; alter `issues` (`review_task_id`); alter `chapters`/`scenes`/`segments`/`speaker_attributions` (`auto_accepted`, `decision_tier`; attributions also `review_task_id`) | extraction-pipeline-v2 steps 6–7 |
| **C — Casting** | 0027 | +`voice_catalog_entries`, +`casting_decisions`; alter `voice_profiles` (`voice_catalog_entry_id`), `character_voice_assignments` (`user_locked`, `locked_reason`, `casting_decision_id`), `project_production_settings` (`narrator_casting_decision_id`, `casting_style_preset`, `auto_cast_enabled`) | automatic-casting-v2 steps 1–2 |
| **D — TTS identity/registry** | 0028 | +`tts_engine_models`; alter `voice_catalog_entries` (`seed`, `reference_audio_path`, `acting_refs_json`, `engine_model_version`) — *these columns are added in D, not C, because they land with the expressive-engine bake-off* | tts-engine-strategy steps 3–4 |
| **E — Sound design** | 0029 | alter `scenes` (`atmosphere_profile_json`); alter `ambience_assets` (`model`, `prompt`, `seed`, `cache_key`, `qa_status`; widen `provenance`); alter `ambience_cues` (`origin`, `evidence_json`, `muted`, `user_locked`); alter `project_production_settings` (`auto_sound_design_json`) | generative-sound-design steps 2–4 |
| **F — Voice bible** | 0030 | +`voice_bibles`; alter `project_production_settings` (`voice_bible_id`) | voice-bible + casting enforcement |
| **G — Series continuity (deferred)** | 0031 | +`series_character_voice_links`; alter `projects` (`series_id`) | automatic-casting-v2 §7 (phase 2) |

Batches C and D touch `voice_catalog_entries` in sequence; C creates it with the casting
facet columns, D adds the identity columns. Batch B's `voice_catalog_entry_id` FK on
`voice_profiles` is in C (it depends on the table existing) — the ordering above respects
every FK dependency.

**Backward-compatibility rules.**

- Widened enums (`jobs.status` gaining `RESUMABLE`/`CANCELED`; `ambience_assets.provenance`
  gaining `generated`/`bank`) only *add* values; existing values are untouched.
- `structure_parser_warnings` rows remain readable; the pipeline simply stops emitting the
  per-segment firehose. No data is deleted by a migration.
- All new decision/lock columns default to the "v1 behavior" (`auto_accepted=false`,
  `user_locked=false`, `origin='user_created'`, `provenance='uploaded'`).

**Data backfill algorithms** (run as idempotent jobs, not in the migration transaction):

1. **Voice catalog backfill.** After Batch C, run one audition job per installed engine
   (`POST /voice-catalog/audition-jobs`): for each native voice, synthesize the audition
   paragraph, extract acoustics, LLM-label, persist a `voice_catalog_entries` row + WAV +
   `.npy`. Idempotent, keyed `(engine, engine_version, engine_voice_id)`; re-runs only on
   engine-version change.
2. **Hand-assigned voices → locked.** After Batch C, for every `character_voice_assignments`
   row with `casting_decision_id IS NULL`, set `user_locked = true`. Guarantees the first
   auto-cast run never clobbers a human's prior decision (casting-v2 override model).
3. **Interrupted jobs.** On first startup after Batch A, `reconcile_interrupted` sets every
   `RUNNING` job to `RESUMABLE` (was `FAILED`); the orchestrator re-plans from checkpoints.
   No historical job rows are rewritten beyond this status remap.
4. **Ambience defaults.** Batch E defaults make every existing asset `provenance='uploaded'`
   and every existing cue `origin='user_created'`, `muted=false`, `user_locked=false` — no
   row-level backfill needed (defaults suffice).
5. **Atmosphere profiles.** Not backfilled; populated lazily by the first sound-plan run per
   chapter (a scene with `atmosphere_profile_json = '{}'` simply gets no ambience until
   planned).

## 7. Integrity & concurrency

SQLite is **single-writer**; WAL + a 30 s busy timeout are already on. Under v2's high
fan-out, thousands of checkpoint/event writes per second can hit that timeout, so:

- **Single writer task.** All checkpoint/event/cache writes are routed through one writer
  task/queue (target-architecture §10); the worker pools are readers. Batches of checkpoint
  updates are coalesced.
- **`BEGIN IMMEDIATE` (reserve the write lock up front) is required for** any
  read-modify-write that must be atomic under concurrency:
  - segment render insert + active-pointer update (existing `rendering.py` pattern — kept);
  - `casting_decisions` supersession (insert new + set prior `superseded_by_id`) — must be
    one immediate transaction so the partial-unique "one active per character" index can
    never see two active rows;
  - `review_tasks` fold-in (find-open-task-or-create + append member) — immediate, so two
    stages folding into the same `cause_key` can't both create the task;
  - `inference_cache` upsert (check-then-insert) and `hit_count` bump;
  - `job_checkpoints` claim (`pending → running`), so two workers can't both run a unit.
- **Read-only** paths (list endpoints, event replay, distinctiveness scoring reads) never
  take `BEGIN IMMEDIATE`.

**New unique / partial indexes (summary).**

| Index | Table | Kind | Guarantees |
|---|---|---|---|
| PK(`unit_key`) | `job_checkpoints` | unique | one record per content-addressed unit (idempotent resume) |
| PK(`cache_key`) | `inference_cache` | unique | one cache entry per inference key |
| `(project_id, cause_key) WHERE status='open'` | `review_tasks` | partial unique | no duplicate open task per cause |
| `(project_id, character_id) WHERE superseded_by_id IS NULL AND role='character'` | `casting_decisions` | partial unique | one active decision per character |
| `(project_id) WHERE superseded_by_id IS NULL AND role='narrator'` | `casting_decisions` | partial unique | one active narrator decision |
| `(engine, engine_version, engine_voice_id)` | `voice_catalog_entries` | unique (voice_id not null) | idempotent audition upsert |
| `(engine, model_version)` | `tts_engine_models` | unique | one capability contract per engine model |
| `(series_id, canonical_character_key)` | `series_character_voice_links` | unique | one series link per canonical character |
| `uq_segment_renders_succeeded_key` | `segment_renders` | partial unique (existing) | one succeeded render per key — **unchanged** |

**Append-only chains extend to new entities.** The existing `segment_renders`
(`parent_render_id`) / `chapter_renders` chains are joined by: `casting_decisions`
(`superseded_by_id` chain — each rerun appends, never overwrites), `ambience_assets`
(regenerate appends a new row; the cue re-points), `job_events` (monotonic `event_id`,
never mutated), and `voice_catalog_entries` identity re-validation on a model bump (a
material mismatch appends a new entry / raises a "stale voice" issue rather than silently
mutating the stored identity — tts §6.4). No v2 entity mutates history in place.

## 8. Open questions

- **Cache scope.** Is `inference_cache` cross-project (shared model warmups, as specified)
  or project-scoped? Cross-project maximizes hit-rate (a bed generated for book A serves
  book B) but complicates per-project export/delete. (target-architecture §10.)
- **Inline embedding cache.** Do we add `voice_catalog_entries.embedding_json` as a
  query-side cache if path I/O dominates distinctiveness scoring? Allowed by §4, deferred
  until measured (§3.3).
- **Decision audit granularity.** Per-entity `auto_accepted`/`decision_tier` columns
  (chosen here) vs a unified `decision_audit` table. Columns keep the per-entity
  append-only model clean; a unified table would ease cross-stage "why was this
  auto-accepted?" analytics. Revisit if a global audit view is needed.
- **Sub-unit checkpointing.** Do very long TTS segments checkpoint below segment level, or
  is segment-level the floor (keeping the segment atomic)? (target-architecture §10.)
- **`cast_reconcile` blocking export.** May reconciliation ever block the first export, or
  is a "voices still converging" advisory sufficient? Affects whether `casting_decisions`
  needs a `provisional` flag distinct from `superseded_by_id`. (target-architecture §10.)
- **Voice-bible ownership of do-not-cross rules.** They are recorded in `bible_json` but
  *enforced* in casting/render code. If a future UI needs to query "which rule fired",
  those may need promotion to a small `voice_bible_rule_checks` child table.
- **Series canonical-key stability.** `canonical_character_key` normalization must be
  stable across projects without silently merging distinct characters (§3.7); the exact
  normalization + confirmation UX is unspecified pending the phase-2 build.
- **`job_events` retention vs. debug bundles.** The 7-day/last-200 pruning may drop events a
  post-mortem wants; do failed jobs pin their full event history into the debug bundle
  before pruning? (target-architecture §8.)
