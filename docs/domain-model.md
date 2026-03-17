# Domain Model

See also: [architecture.md](architecture.md), [db-schema.md](db-schema.md), [pipeline-manifest-spec.md](pipeline-manifest-spec.md), [voice-bible-spec.md](voice-bible-spec.md)

## Core hierarchy
```text
Project
├─ SourceDocument
├─ Chapter
│  ├─ Scene
│  │  └─ Segment
│  └─ ChapterRender
├─ Character
├─ VoiceProfile
├─ PronunciationEntry
├─ SegmentRender
├─ Issue
├─ Comment
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
- `original_path`
- `normalized_text_path`
- `checksum`
- `parser_version`
- `word_count`

### Chapter
Major content division inside a project.

Fields:
- `id`
- `project_id`
- `chapter_number`
- `title`
- `order_index`
- `word_count`
- `status`

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
- `title`
- `mood_tags`
- `style_preset`
- `ambience_profile`
- `start_offset`
- `end_offset`

### Segment
Atomic editable and renderable unit.

Fields:
- `id`
- `scene_id`
- `order_index`
- `segment_type`
- `speaker_character_id`
- `text_content`
- `normalized_text`
- `attribution_confidence`
- `direction`
- `duration_ms`
- `status`
- `current_render_id`

Segment types:
- `narration`
- `dialogue`
- `monologue`
- `silence`
- `ambience_cue`
- `sfx_cue`

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
- only one active `current_render_id` at a time
- regeneration creates a new render rather than overwriting history
- a segment cannot be approved without a valid active render

### Character
Story speaker or speaker-like role.

Fields:
- `id`
- `project_id`
- `display_name`
- `aliases`
- `description`
- `role_type`
- `notes`

Role types:
- `narrator`
- `major`
- `minor`
- `ambient_voice`
- `unknown`

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
- `voice_profile_id`
- `backend`
- `backend_model_version`
- `render_params`
- `speech_audio_path`
- `alignment_json_path`
- `waveform_json_path`
- `duration_ms`
- `qa_summary`
- `created_at`

Rules:
- append-only history
- never overwritten in place
- active render is referenced by `segments.current_render_id`

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

### ExportPackage
Export artifact record.

Fields:
- `id`
- `project_id`
- `format`
- `scope`
- `metadata`
- `output_path`
- `status`

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
