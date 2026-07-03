# Domain Model

See also: [architecture.md](../architecture/architecture.md), [db-schema.md](db-schema.md), [pipeline-manifest-spec.md](../architecture/pipeline-manifest-spec.md), [voice-bible-spec.md](../pipeline/casting/voice-bible-spec.md)

## Core hierarchy
```text
Project
├─ SourceDocument
│  ├─ SourcePage
│  ├─ OcrRun
│  ├─ CanonicalSpan
│  └─ TextCleanlinessIssue
├─ Chapter
│  ├─ Scene
│  │  └─ Segment
│  └─ ChapterRender
├─ StructureParserWarning
├─ Character
├─ VoiceProfile
├─ PronunciationEntry
├─ SegmentRender
├─ LlmRun
├─ Issue
├─ Comment
├─ PatchAttempt
├─ SegmentReviewInspector
├─ ExportBlocker
├─ ExportEstimate
├─ ExportPackage
└─ RightsDeclaration
```

## Entity definitions
### Project
Top-level audiobook production workspace.

Fields:
- `id`
- `title`
- `author`
- `description`
- `rights_status`
- `status`
- `settings`
- `created_at`
- `updated_at`

Lifecycle states:
- `draft`
- `structured`
- `cast_configured`
- `generating`
- `reviewing`
- `ready_for_export`
- `exported`
- `archived`

Rules:
- cannot export without a rights declaration
- moves to `structured` only after structure generation completes successfully

### SourceDocument
Imported source text record.

Fields:
- `id`
- `project_id`
- `original_filename`
- `mime_type`
- `original_path`
- `canonical_path`
- `manifest_path`
- `checksum`
- `parser_version`
- `status`
- `warnings`

### SourcePage
Page-level extraction metadata for imported sources, especially PDFs.

Fields:
- `id`
- `source_document_id`
- `page_number`
- `image_path`
- `embedded_text_path`
- `selected_text_path`
- `extraction_method`
- `confidence`
- `warnings`

### OcrRun
Local OCR run metadata for low-text PDF pages.

Fields:
- `id`
- `source_document_id`
- `provider`
- `status`
- `settings`
- `started_at`
- `completed_at`
- `error_message`

### CanonicalSpan
Approximate mapping from selected source page text to canonical manuscript offsets.

Fields:
- `id`
- `source_document_id`
- `page_number`
- `canonical_start_offset`
- `canonical_end_offset`
- `source_text_hash`
- `bbox`
- `extraction_method`
- `confidence`

### TextCleanlinessIssue
Reviewable clean-text decision or suspicious-token finding created during ingestion.

Fields:
- `id`
- `source_document_id`
- `canonical_span_start`
- `canonical_span_end`
- `issue_type`
- `severity`
- `suggested_fix`
- `confidence`
- `status`
- `resolved_by_user`

### Chapter
Major content division inside a project.

Fields:
- `id`
- `project_id`
- `title`
- `order_index`
- `start_offset`
- `end_offset`
- `confidence`
- `status`
- `parser_evidence`
- `user_locked`
- `lock_reason`

Lifecycle states:
- `pending`
- `structured`
- `ready_for_generation`
- `generating`
- `generated`
- `needs_review`
- `approved`
- `exported`

### Scene
Scene-level organizational unit within a chapter.

Fields:
- `id`
- `chapter_id`
- `order_index`
- `start_offset`
- `end_offset`
- `confidence`
- `status`
- `parser_evidence`
- `user_locked`
- `lock_reason`

### Segment
Atomic editable and renderable unit.

Fields:
- `id`
- `scene_id`
- `order_index`
- `segment_type`
- `speaker_candidate`
- `speaker_confidence`
- `text_content`
- `normalized_text`
- `start_offset`
- `end_offset`
- `revision`
- `status`
- `parser_evidence`
- `user_locked`
- `lock_reason`

Segment types:
- `narration`
- `dialogue`
- `performance_beat`

Lifecycle states:
- `pending`
- `ready`
- `generating`
- `generated`
- `qa_flagged`
- `needs_review`
- `approved`
- `superseded`

Rules:
- locked segments are preserved across parser reruns
- regeneration creates a new render rather than overwriting history
- segment split/merge creates reviewable revisions

### StructureParserWarning
Parser warning or confidence note anchored to a chapter, scene, or segment.

Fields:
- `id`
- `project_id`
- `source_document_id`
- `scope_type`
- `scope_id`
- `severity`
- `message`
- `evidence`
- `confidence`
- `resolved`
- `created_at`

### LlmRun
Local LLM extraction attempt with prompt, schema, response, and fail-closed status.

Fields:
- `id`
- `project_id`
- `source_document_id`
- `provider`
- `model`
- `task`
- `status`
- `prompt_path`
- `response_path`
- `schema`
- `result`
- `error_message`
- `retries`
- `started_at`
- `completed_at`

### Character
Story speaker or speaker-like role.

Fields:
- `id`
- `project_id`
- `display_name`
- `canonical_name`
- `aliases`
- `traits`
- `first_seen_source_id`
- `first_seen_chapter_id`
- `first_seen_segment_id`
- `role_type`
- `confidence`
- `notes`
- `merge_history`
- `split_history`
- `user_locked`
- `lock_reason`
- `merged_into_character_id`
- `voice_profile_id`

Role types:
- `narrator`
- `major`
- `supporting`
- `minor`
- `unknown`

Rules:
- canonical manuscript text stays separate from Character Bible metadata
- merge and split operations append history instead of deleting records
- user locks survive reruns and local LLM extraction passes
- voice links are project-local references to `VoiceProfile` records

### SpeakerAttribution
Reviewed speaker decision for one segment.

Fields:
- `id`
- `project_id`
- `segment_id`
- `character_id`
- `speaker_name`
- `method`
- `evidence`
- `confidence`
- `status`
- `user_locked`
- `voice_profile_id`
- `created_at`
- `updated_at`

Rules:
- one active attribution row exists per segment after Cast Review
- `status=needs_review` keeps uncertain speakers visible
- `user_locked=true` protects manual decisions from reruns
- approved attributions resolve to the linked character voice when available

### SegmentDirection
Reviewed delivery direction for one segment.

Fields:
- `segment_id`
- `project_id`
- `direction`
- `source`
- `user_locked`
- `direction_fingerprint`
- `created_at`
- `updated_at`

Direction fields:
- `emotion`
- `pace`
- `intensity`
- `pause_before_ms`
- `pause_after_ms`
- `emphasis`
- `whisper`
- `style_prompt`

Rules:
- emotion is restricted to the controlled local taxonomy
- manual saves lock the row by default
- deterministic inference skips locked rows
- render freshness compares the resolved direction payload

### VoiceProfile
Reusable voice configuration.

Fields:
- `id`
- `project_id`
- `name`
- `backend`
- `base_voice_id`
- `style_prompt`
- `settings`
- `sample_audio_path`
- `is_narrator_default`

Rules:
- multiple characters may share a supporting voice in MVP
- at most one narrator-default voice per project

### SegmentRender
Immutable generation output for one segment.

Fields:
- `id`
- `segment_id`
- `render_key`
- `status`
- `audio_path`
- `metadata_path`
- `duration_ms`
- `parent_render_id`
- `audio_url`

Rules:
- append-only history
- never overwritten in place
- request metadata stores canonical text, synthesis text, provider identity, voice, direction, and applied pronunciations
- forced regeneration links the new row to its previous render through `parent_render_id`

### SegmentRenderComparison
Latest-vs-parent render comparison for one segment.

Fields:
- `segment_id`
- `current_render`
- `previous_render`
- `changed_fields`

### PatchAttempt
Append-only record that links a review patch to the old segment render, new segment render, and reassembled chapter render.

Fields:
- `id`
- `issue_id`
- `segment_id`
- `old_render_id`
- `new_render_id`
- `chapter_render_id`
- `created_at`

### SegmentReviewInspector
Read model for the Review & Patch Workbench. It is assembled from existing DB rows and artifact metadata, not stored as a separate table.

Fields:
- `project_id`
- `chapter_id`
- `chapter_title`
- `scene_id`
- `segment`
- `source_text`
- `canonical_text`
- `structure`
- `cast`
- `direction`
- `render_history`
- `waveform`
- `qa_issues`
- `comments`
- `patch_queue`

### RenderQueueItem
Per-segment queue row for chapter production.

Fields:
- `id`
- `project_id`
- `chapter_id`
- `segment_id`
- `job_id`
- `status`
- `voice_profile_id`
- `provider`
- `render_key`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

### TtsProviderInfo
Read-only status for a local TTS provider.

Fields:
- `provider`
- `display_name`
- `setup_mode`
- `ready`
- `message`
- `available_voices`
- `capabilities`
- `requires_reference_consent`
- `reference_voice_consent`
- `reference_voice_path`

### ChapterRender
Assembled chapter output.

Fields:
- `id`
- `chapter_id`
- `render_mode`
- `speech_stem_path`
- `ambience_stem_path`
- `mixed_audio_path`
- `manifest_path`
- `duration_ms`
- `status`

### SoundAsset
Local sound design asset metadata.

Fields:
- `id`
- `project_id`
- `name`
- `asset_type`
- `asset_path`
- `audio_url`
- `duration_ms`
- `license_note`
- `provenance`

### SoundCue
Scene-level assignment of a sound asset into a chapter mix.

Fields:
- `id`
- `scene_id`
- `asset_id`
- `cue_type`
- `start_ms`
- `gain_db`
- `fade_in_ms`
- `fade_out_ms`
- `ducking`
- `render_mode`
- `no_sfx`

### ReadinessReport
Persisted deterministic QA snapshot.

Fields:
- `id`
- `project_id`
- `chapter_id`
- `status`
- `score`
- `summary`
- `checks`
- `created_at`

### ReadinessCheck
Individual readiness check result.

Fields:
- `id`
- `scope`
- `status`
- `severity`
- `category`
- `title`
- `description`
- `issue_id`
- `resolution_status`
- `metadata`

### PronunciationEntry
Pronunciation or replacement override.

Fields:
- `id`
- `project_id`
- `term`
- `phonetic`
- `replacement_text`
- `notes`

### Issue
QA or editorial finding.

Fields:
- `id`
- `project_id`
- `chapter_id`
- `scene_id`
- `segment_id`
- `severity`
- `category`
- `title`
- `description`
- `status`
- `metadata`

Severities:
- `info`
- `warning`
- `error`
- `blocking`

### Comment
Human feedback anchored to project items.

Fields:
- `id`
- `project_id`
- `chapter_id`
- `segment_id`
- `body`
- `created_by`
- `created_at`

### ExportBlocker
Deterministic reason an export request cannot be packaged.

Fields:
- `code`
- `severity`
- `message`
- `scope`
- `chapter_id`
- `issue_id`

### ExportEstimate
Preflight result for an export request.

Fields:
- `project_id`
- `format`
- `audio_variant`
- `chapter_count`
- `estimated_size_bytes`
- `blockers`
- `metadata`
- `m4b_planned`

### ExportPackage
Completed local export package.

Fields:
- `id`
- `project_id`
- `format`
- `status`
- `output_path`
- `manifest_path`
- `archive_path`
- `download_url`
- `audio_variant`
- `chapter_count`
- `estimated_size_bytes`
- `checksum`
- `metadata`
- `manifest_summary`
- `blockers`

### RightsDeclaration
User rights assertion used for export gating.

Fields:
- `id`
- `project_id`
- `declaration_type`
- `status`
- `evidence_path`
- `notes`

## Relationships
- a `Project` has one `SourceDocument`
- a `Project` has many `Chapters`
- a `Chapter` has many `Scenes`
- a `Scene` has many `Segments`
- a `Project` has many `Characters`, `VoiceProfiles`, `PronunciationEntries`, `Issues`, `Comments`, and `ExportPackages`
- a `Character` may have one active voice assignment
- a `Segment` may reference one `Character` as speaker
- a `Segment` has many `SegmentRenders`
- a `Segment` has many `PatchAttempts`
- a `Chapter` has many `ChapterRenders`

## Lifecycle rules
### Project
1. create project
2. import source
3. structure content
4. configure cast
5. generate audio
6. review issues
7. export outputs

### Segment
1. segment created
2. direction applied
3. render requested
4. render stored
5. QA evaluated
6. segment approved or regenerated

### Chapter
1. chapter structured
2. active segment renders available
3. chapter assembled
4. chapter QA evaluated
5. chapter reviewed
6. chapter approved
7. chapter included in export

## Invariants
- `order_index` is unique within chapter or scene scope
- a segment cannot be `approved` without a valid active render
- a chapter cannot be `approved` while blocking issues exist
- export requires approved chapter renders and a valid rights declaration
- active render history must remain traceable

## Domain events
- `ProjectCreated`
- `SourceImported`
- `StructureGenerated`
- `VoiceAssigned`
- `SegmentRenderRequested`
- `SegmentRendered`
- `ChapterAssembled`
- `QualityReportGenerated`
- `IssueCreated`
- `SegmentApproved`
- `ExportRequested`
- `ExportCompleted`
