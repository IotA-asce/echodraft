# Database Schema

See also: [domain-model.md](domain-model.md), [pipeline-manifest-spec.md](pipeline-manifest-spec.md), [api-spec.yaml](api-spec.yaml)

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

### `chapters`
Purpose: chapter-level structure.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `chapter_number` INTEGER
- `title` TEXT
- `order_index` INTEGER NOT NULL
- `word_count` INTEGER
- `status` TEXT NOT NULL

Constraints:
- unique `(project_id, order_index)`

### `scenes`
Purpose: scene-level organization within chapters.

Key columns:
- `id` TEXT PK
- `chapter_id` FK
- `order_index` INTEGER NOT NULL
- `title` TEXT
- `mood_tags_json` TEXT
- `style_preset` TEXT
- `ambience_profile` TEXT
- `start_offset` INTEGER
- `end_offset` INTEGER

Constraints:
- unique `(chapter_id, order_index)`

### `characters`
Purpose: speaker registry.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `display_name` TEXT NOT NULL
- `aliases_json` TEXT
- `description` TEXT
- `role_type` TEXT
- `notes` TEXT

Indexes:
- `(project_id, display_name)`

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
- `segment_type` TEXT NOT NULL
- `speaker_character_id` FK nullable
- `text_content` TEXT NOT NULL
- `normalized_text` TEXT
- `attribution_confidence` REAL
- `direction_json` TEXT
- `duration_ms` INTEGER
- `status` TEXT NOT NULL
- `current_render_id` TEXT nullable

Constraints:
- unique `(scene_id, order_index)`

Indexes:
- `speaker_character_id`
- `status`

### `segment_renders`
Purpose: immutable segment render history.

Key columns:
- `id` TEXT PK
- `segment_id` FK
- `voice_profile_id` FK
- `backend` TEXT NOT NULL
- `backend_model_version` TEXT
- `render_params_json` TEXT
- `speech_audio_path` TEXT NOT NULL
- `alignment_json_path` TEXT
- `waveform_json_path` TEXT
- `duration_ms` INTEGER
- `qa_summary_json` TEXT
- `created_at` DATETIME

Indexes:
- `(segment_id, created_at)`

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
- `created_at` DATETIME

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
Purpose: export job outputs.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `format` TEXT NOT NULL
- `scope` TEXT NOT NULL
- `metadata_json` TEXT
- `output_path` TEXT
- `status` TEXT NOT NULL

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
7. `chapters`
8. `scenes`
9. `characters`
10. `voice_profiles`
11. `character_voice_assignments`
12. `pronunciation_entries`
13. `segments`
14. `segment_renders`
15. `chapter_renders`
16. `issues`
17. `comments`
18. `exports`
19. `jobs`
20. `model_installations`
21. `model_install_jobs`
22. `rights_declarations`

## Lifecycle semantics
- `segments.current_render_id` points to the active immutable render.
- Regeneration inserts a new `segment_renders` row instead of mutating existing rows.
- Segment changes stale downstream chapter renders.
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
