# Database Schema

See also: [domain-model.md](domain-model.md), [pipeline-manifest-spec.md](../architecture/pipeline-manifest-spec.md), [api-spec.yaml](../api/api-spec.yaml)

## Database strategy
### MVP
- SQLite for local-first execution
- Alembic-managed migrations
- JSON fields stored as JSON text where practical

### Later
- Postgres for hosted or multi-user scale
- Same core entity model, expanded with org/user/audit tables

## Design principles
- Store metadata in the relational database.
- Store binary audio, manifests, and large derived artifacts in filesystem or object storage.
- Preserve append-only render history.
- Use explicit foreign keys for traceability.
- Keep schema aligned with segment-first invalidation rules.

## Core tables
### `projects`
Purpose: top-level project workspace.

Key columns:
- `id` TEXT PK
- `title` TEXT NOT NULL
- `author` TEXT
- `description` TEXT
- `rights_status` TEXT NOT NULL
- `status` TEXT NOT NULL
- `settings_json` TEXT
- `created_at` DATETIME
- `updated_at` DATETIME

### `source_documents`
Purpose: append-only record of each imported or reparsed source manuscript.

Key columns:
- `id` TEXT PK
- `project_id` FK UNIQUE
- `original_path` TEXT NOT NULL
- `normalized_text_path` TEXT NOT NULL
- `checksum` TEXT
- `parser_version` TEXT
- `word_count` INTEGER

Stage 01 columns:
- `original_filename` TEXT NOT NULL
- `mime_type` TEXT NOT NULL
- `checksum` TEXT NOT NULL
- `imported_at` DATETIME NOT NULL
- `rights_status` TEXT NOT NULL
- `parser_version` TEXT NOT NULL
- `original_path` TEXT NOT NULL
- `canonical_path` TEXT nullable
- `manifest_path` TEXT nullable
- `warnings_json` TEXT NOT NULL
- `status` TEXT NOT NULL
- `error_message` TEXT nullable

### `source_pages`
Purpose: page-level extraction metadata for source documents, especially PDFs.

Key columns:
- `id` TEXT PK
- `source_document_id` FK
- `page_number` INTEGER NOT NULL
- `image_path` TEXT nullable
- `embedded_text_path` TEXT nullable
- `selected_text_path` TEXT nullable
- `extraction_method` TEXT NOT NULL
- `confidence` REAL NOT NULL
- `warnings_json` TEXT NOT NULL

### `ocr_runs`
Purpose: OCR provider run metadata for one source document.

Key columns:
- `id` TEXT PK
- `source_document_id` FK
- `provider` TEXT NOT NULL
- `status` TEXT NOT NULL
- `settings_json` TEXT NOT NULL
- `started_at` DATETIME NOT NULL
- `completed_at` DATETIME nullable
- `error_message` TEXT nullable

### `ocr_page_results`
Purpose: per-page OCR output artifacts.

Key columns:
- `id` TEXT PK
- `ocr_run_id` FK
- `source_page_id` FK
- `page_number` INTEGER NOT NULL
- `text_path` TEXT NOT NULL
- `json_path` TEXT NOT NULL
- `confidence` REAL NOT NULL
- `warnings_json` TEXT NOT NULL

### `canonical_spans`
Purpose: mapping from selected source page text to canonical text offsets.

Key columns:
- `id` TEXT PK
- `source_document_id` FK
- `page_number` INTEGER NOT NULL
- `canonical_start_offset` INTEGER NOT NULL
- `canonical_end_offset` INTEGER NOT NULL
- `source_text_hash` TEXT NOT NULL
- `bbox_json` TEXT nullable
- `extraction_method` TEXT NOT NULL
- `confidence` REAL NOT NULL

### `cleaning_runs`
Purpose: metadata for deterministic clean-text passes performed before canonical normalization.

Key columns:
- `id` TEXT PK
- `source_document_id` FK
- `status` TEXT NOT NULL
- `manifest_path` TEXT nullable
- `started_at` DATETIME NOT NULL
- `completed_at` DATETIME nullable
- `error_message` TEXT nullable

### `text_cleanliness_issues`
Purpose: reviewable applied cleaning decisions and open suspicious-text findings.

Key columns:
- `id` TEXT PK
- `source_document_id` FK
- `canonical_span_start` INTEGER NOT NULL
- `canonical_span_end` INTEGER NOT NULL
- `issue_type` TEXT NOT NULL
- `severity` TEXT NOT NULL
- `suggested_fix` TEXT nullable
- `confidence` REAL NOT NULL
- `status` TEXT NOT NULL
- `resolved_by_user` BOOLEAN NOT NULL

### `chapters`
Purpose: chapter-level structure.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `title` TEXT
- `order_index` INTEGER NOT NULL
- `start_offset` INTEGER NOT NULL
- `end_offset` INTEGER NOT NULL
- `confidence` REAL NOT NULL
- `status` TEXT NOT NULL
- `parser_evidence_json` TEXT NOT NULL
- `user_locked` BOOLEAN NOT NULL
- `lock_reason` TEXT nullable

### `scenes`
Purpose: scene-level organization within chapters.

Key columns:
- `id` TEXT PK
- `chapter_id` FK
- `order_index` INTEGER NOT NULL
- `start_offset` INTEGER NOT NULL
- `end_offset` INTEGER NOT NULL
- `confidence` REAL NOT NULL
- `status` TEXT NOT NULL
- `parser_evidence_json` TEXT NOT NULL
- `user_locked` BOOLEAN NOT NULL
- `lock_reason` TEXT nullable

### `structure_parser_warnings`
Purpose: parser warnings, confidence notes, and evidence attached to chapter, scene, or segment scopes.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `source_document_id` FK nullable
- `scope_type` TEXT NOT NULL
- `scope_id` TEXT NOT NULL
- `severity` TEXT NOT NULL
- `message` TEXT NOT NULL
- `evidence_json` TEXT NOT NULL
- `confidence` REAL NOT NULL
- `resolved` BOOLEAN NOT NULL
- `created_at` DATETIME NOT NULL

### `structure_locks`
Purpose: user locks that protect editorial structure decisions from later parser runs.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `scope_type` TEXT NOT NULL
- `scope_id` TEXT NOT NULL
- `reason` TEXT nullable
- `created_at` DATETIME NOT NULL

### `characters`
Purpose: editable Character Bible and speaker registry.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `display_name` TEXT NOT NULL
- `canonical_name` TEXT nullable
- `aliases_json` TEXT
- `traits_json` TEXT
- `first_seen_source_id` TEXT nullable
- `first_seen_chapter_id` TEXT nullable
- `first_seen_segment_id` TEXT nullable
- `role_type` TEXT
- `confidence` REAL
- `notes` TEXT
- `merge_history_json` TEXT
- `split_history_json` TEXT
- `user_locked` BOOLEAN
- `lock_reason` TEXT nullable
- `merged_into_character_id` TEXT nullable

Indexes:
- `(project_id, display_name)`

Rules:
- merge/split history is append-only JSON metadata
- merged source records remain for traceability and point at `merged_into_character_id`
- voice links live in `character_voice_assignments`

### `voice_profiles`
Purpose: reusable voice configurations.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `name` TEXT NOT NULL
- `backend` TEXT NOT NULL
- `base_voice_id` TEXT
- `style_prompt` TEXT
- `settings_json` TEXT
- `sample_audio_path` TEXT
- `is_narrator_default` INTEGER NOT NULL DEFAULT 0

### `character_voice_assignments`
Purpose: map characters to voice profiles.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `character_id` FK
- `voice_profile_id` FK

Constraints:
- unique `(project_id, character_id)`

### `speaker_attributions`
Purpose: active Cast Review decision for one segment.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `segment_id` FK unique
- `character_id` FK nullable
- `speaker_name` TEXT nullable
- `method` TEXT
- `evidence_json` TEXT
- `confidence` REAL
- `status` TEXT
- `user_locked` BOOLEAN
- `created_at` DATETIME
- `updated_at` DATETIME

Rules:
- one active attribution row per segment
- deterministic reruns skip `user_locked` rows
- approved rows with character voice assignments are used for production voice resolution
- segment voice overrides still take precedence over speaker attribution voices

### `segment_directions`
Purpose: active Direction Studio settings for one segment.

Key columns:
- `segment_id` FK PK
- `project_id` FK
- `direction_json` TEXT
- `source` TEXT
- `user_locked` BOOLEAN
- `direction_fingerprint` TEXT
- `created_at` DATETIME
- `updated_at` DATETIME

Rules:
- one active direction row per segment
- inference skips locked rows
- production resolves direction from segment override, then `segment_directions`, then project default
- render cache keys include the resolved direction payload

### `pronunciation_entries`
Purpose: pronunciation overrides.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `term` TEXT NOT NULL
- `phonetic` TEXT
- `replacement_text` TEXT
- `notes` TEXT

Indexes:
- `(project_id, term)`

### `segments`
Purpose: atomic generation and review unit.

Key columns:
- `id` TEXT PK
- `scene_id` FK
- `order_index` INTEGER NOT NULL
- `text_content` TEXT NOT NULL
- `normalized_text` TEXT NOT NULL
- `segment_type` TEXT NOT NULL
- `speaker_candidate` TEXT nullable
- `speaker_confidence` REAL NOT NULL
- `start_offset` INTEGER NOT NULL
- `end_offset` INTEGER NOT NULL
- `revision` INTEGER NOT NULL
- `status` TEXT NOT NULL
- `parser_evidence_json` TEXT NOT NULL
- `user_locked` BOOLEAN NOT NULL
- `lock_reason` TEXT nullable

### `segment_renders`
Purpose: immutable segment render history.

Key columns:
- `id` TEXT PK
- `segment_id` FK
- `render_key` TEXT NOT NULL
- `status` TEXT NOT NULL
- `audio_path` TEXT NOT NULL
- `metadata_path` TEXT NOT NULL
- `duration_ms` INTEGER NOT NULL
- `parent_render_id` TEXT nullable
- `request_json` TEXT NOT NULL
- `created_at` DATETIME nullable (NULL only on legacy rows; latest-render selection orders by `created_at DESC, id DESC`)

Indexes:
- `segment_id`

### `render_queue_items`
Purpose: per-segment production queue status for chapter render jobs.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `chapter_id` FK
- `segment_id` FK
- `job_id` FK
- `status` TEXT NOT NULL
- `voice_profile_id` FK nullable
- `provider` TEXT NOT NULL
- `render_key` TEXT nullable
- `error_message` TEXT nullable
- `created_at` DATETIME NOT NULL
- `started_at` DATETIME nullable
- `finished_at` DATETIME nullable

Notes:
- queue rows store metadata and render references only
- audio remains in artifact storage under the project directory

### `ambience_assets`
Purpose: local sound asset metadata for ambience, music, and SFX.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `name` TEXT NOT NULL
- `asset_type` TEXT NOT NULL
- `asset_path` TEXT NOT NULL
- `duration_ms` INTEGER nullable
- `license_note` TEXT NOT NULL
- `provenance` TEXT NOT NULL

Notes:
- audio files live under project artifacts or a registered local path
- no audio blobs are stored in the relational DB

### `ambience_cues`
Purpose: scene-level sound design cue assignment.

Key columns:
- `id` TEXT PK
- `scene_id` FK
- `asset_id` FK nullable
- `cue_type` TEXT NOT NULL
- `start_ms` INTEGER NOT NULL
- `gain_db` REAL NOT NULL
- `fade_in_ms` INTEGER NOT NULL
- `fade_out_ms` INTEGER NOT NULL
- `ducking` BOOLEAN NOT NULL
- `render_mode` TEXT NOT NULL
- `no_sfx` BOOLEAN NOT NULL

Rules:
- light and dramatized assembly read these cues into chapter manifests
- clean chapter assembly ignores cues and writes speech only

### `chapter_renders`
Purpose: chapter-level assembled outputs.

Key columns:
- `id` TEXT PK
- `chapter_id` FK
- `render_mode` TEXT NOT NULL
- `speech_stem_path` TEXT
- `ambience_stem_path` TEXT
- `mixed_audio_path` TEXT
- `manifest_path` TEXT
- `duration_ms` INTEGER
- `status` TEXT NOT NULL
- `created_at` DATETIME nullable (NULL only on legacy rows; latest-render selection orders by `created_at DESC, id DESC`)

Indexes:
- `(chapter_id, created_at)`

### `issues`
Purpose: QA and editorial findings.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `chapter_id` FK nullable
- `scene_id` FK nullable
- `segment_id` FK nullable
- `severity` TEXT NOT NULL
- `category` TEXT NOT NULL
- `title` TEXT NOT NULL
- `description` TEXT
- `status` TEXT NOT NULL
- `metadata_json` TEXT

Indexes:
- `(project_id, status)`
- `(project_id, severity)`

### `readiness_reports`
Purpose: persisted readiness QA snapshots.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `chapter_id` FK nullable
- `status` TEXT NOT NULL
- `score` INTEGER NOT NULL
- `summary_json` TEXT NOT NULL
- `checks_json` TEXT NOT NULL
- `created_at` DATETIME NOT NULL

Rules:
- failed checks link to review issues when action is required
- issue statuses such as `resolved`, `ignored`, and `locked` survive reruns
- reports store metadata only, not audio or manuscript blobs

### `comments`
Purpose: anchored human comments.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `segment_id` FK nullable
- `chapter_id` FK nullable
- `body` TEXT NOT NULL
- `created_by` TEXT
- `created_at` DATETIME

### `exports`
Purpose: export package path/status metadata. Detailed package metadata, QA summary, render lineage, checksums, and cover metadata are stored in `export_manifest.json` under artifacts.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `format` TEXT NOT NULL
- `status` TEXT NOT NULL
- `output_path` TEXT NOT NULL
- `manifest_path` TEXT NOT NULL
- `archive_path` TEXT
- `created_at` DATETIME nullable (NULL only on legacy rows; package listing orders by `created_at DESC, id DESC`)

### `jobs`
Purpose: long-running async operations.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `job_type` TEXT NOT NULL
- `target_id` TEXT
- `payload_json` TEXT
- `status` TEXT NOT NULL
- `error_message` TEXT
- `progress_json` TEXT
- `created_at` DATETIME
- `started_at` DATETIME
- `finished_at` DATETIME

Indexes:
- `(project_id, status)`
- `job_type`

### `model_installations`
Purpose: persisted verification snapshots for local tools and models managed by Model Center.

Key columns:
- `id` TEXT PK
- `model_key` TEXT UNIQUE
- `display_name` TEXT NOT NULL
- `capability` TEXT NOT NULL
- `provider` TEXT NOT NULL
- `version` TEXT nullable
- `install_path` TEXT nullable
- `status` TEXT NOT NULL
- `installed_at` DATETIME nullable
- `last_verified_at` DATETIME nullable
- `size_bytes` INTEGER nullable
- `license_summary` TEXT nullable
- `error_message` TEXT nullable

### `model_install_jobs`
Purpose: Model Center install-job details and log locations linked to generic jobs.

Key columns:
- `id` TEXT PK
- `job_id` FK
- `model_key` TEXT NOT NULL
- `status` TEXT NOT NULL
- `progress_percent` INTEGER NOT NULL
- `current_step` TEXT nullable
- `logs_path` TEXT nullable
- `started_at` DATETIME nullable
- `completed_at` DATETIME nullable
- `error_message` TEXT nullable

### `llm_runs`
Purpose: local LLM extraction attempts, prompts, schemas, responses, and fail-closed status.

Key columns:
- `id` TEXT PK
- `project_id` FK nullable
- `source_document_id` FK nullable
- `provider` TEXT NOT NULL
- `model` TEXT NOT NULL
- `task` TEXT NOT NULL
- `status` TEXT NOT NULL
- `prompt_path` TEXT nullable
- `response_path` TEXT nullable
- `schema_json` TEXT NOT NULL
- `result_json` TEXT nullable
- `error_message` TEXT nullable
- `retries` INTEGER NOT NULL
- `started_at` DATETIME NOT NULL
- `completed_at` DATETIME nullable

### `rights_declarations`
Purpose: rights assertion and export gating.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `declaration_type` TEXT NOT NULL
- `status` TEXT NOT NULL
- `evidence_path` TEXT
- `notes` TEXT
- `created_at` DATETIME
- `updated_at` DATETIME

## Migration order
1. `projects`
2. `source_documents`
3. `source_pages`
4. `ocr_runs`
5. `ocr_page_results`
6. `canonical_spans`
7. `cleaning_runs`
8. `text_cleanliness_issues`
9. `chapters`
10. `scenes`
11. `structure_parser_warnings`
12. `structure_locks`
13. `characters`
14. `voice_profiles`
15. `character_voice_assignments`
16. `pronunciation_entries`
17. `segments`
18. `segment_renders`
19. `chapter_renders`
20. `issues`
21. `comments`
22. `exports`
23. `jobs`
24. `render_queue_items`
25. `model_installations`
26. `model_install_jobs`
27. `llm_runs`
28. `rights_declarations`

## Lifecycle semantics
- Regeneration inserts a new `segment_renders` row instead of mutating existing rows.
- Render queue rows move through queued/running/succeeded/failed and reference render keys when complete.
- Segment changes stale downstream chapter renders.
- Structure locks preserve user-approved segment text across parser reruns.
- Export records always point to a specific output package and status.

## Hosted evolution additions
Later tables likely include:
- `organizations`
- `users`
- `memberships`
- `audit_logs`
- `api_keys`
- `asset_permissions`
- `review_assignments`
- `billing_accounts`

These are additive. They do not replace the MVP core tables above.
