# AI Audiobook Studio — Starter Engineering Pack

This document is the initial implementation pack for the **AI Audiobook Studio** product. It translates the PRDs and engineering roadmap into concrete build artifacts that can guide engineering execution.

Contents:
1. `ARCHITECTURE.md`
2. `DOMAIN_MODEL.md`
3. `API_SPEC.yaml`
4. `DB_SCHEMA.md`
5. `PIPELINE_MANIFEST_SPEC.md`
6. `VOICE_BIBLE_SPEC.md`
7. `QA_RULEBOOK.md`
8. `MVP_EXECUTION_PLAN.md`

---

# 1) ARCHITECTURE.md

## 1.1 Purpose
This document defines the system architecture for the **local-first MVP** and the **evolution path** toward a hybrid/cloud publisher platform.

The product goal is to turn long-form text into a **patchable, multi-voice, high-production audiobook workflow** rather than a one-shot text-to-speech pipeline.

## 1.2 Architectural Goals
- Support long-form book processing in **chapter/scene/segment** units.
- Make every stage **resumable** and **debuggable**.
- Allow selective **segment regeneration** without rerendering full chapters.
- Keep the MVP practical on a **single Apple Silicon machine**.
- Preserve a clean path from local runtime to hosted multi-user platform.

## 1.3 Core Architectural Principles
1. **Segment-first architecture**
   - `Segment` is the smallest atomic unit for generation, QA, review, and patching.
2. **Manifest-driven pipeline**
   - Every stage reads structured input manifests and writes output manifests.
3. **Artifact separation**
   - Metadata goes to the database.
   - Audio and derived artifacts go to filesystem/object storage.
4. **Backend abstraction**
   - TTS backends must be swappable using an adapter interface.
5. **Human-in-the-loop by design**
   - AI output is draftable, inspectable, and revisable.
6. **Local-first privacy**
   - Core workflows must not require cloud upload.

## 1.4 System Context
### External Inputs
- Book/manuscript files: TXT, Markdown, DOCX, EPUB
- Voice profile configuration
- Pronunciation dictionaries
- Ambience/SFX libraries
- User editorial overrides

### Internal System Responsibilities
- Parse and normalize manuscript
- Extract chapters/scenes/segments
- Build character and speaker map
- Assign voices and direction
- Generate segment audio
- Assemble chapters and stems
- Run QA checks
- Support review and patching
- Package exports

## 1.5 MVP Runtime Architecture
```text
[React / Next.js UI]
        |
        v
[FastAPI Backend]
        |
        +--> Project API
        +--> Ingestion Module
        +--> Narrative Module
        +--> Casting Module
        +--> Direction Module
        +--> TTS Module
        +--> Assembly Module
        +--> QA Module
        +--> Review Module
        +--> Export Module
        |
        +--> SQLite
        +--> Local Artifact Store
        +--> Local Model Runtime
```

## 1.6 Future Hosted Architecture
```text
[Web App]
   |
   v
[API Layer]
   |
   +--> Project Service
   +--> Rights Service
   +--> Review Service
   +--> Export Service
   |
   +--> Postgres
   +--> Object Storage
   +--> Queue / Redis
   |
   +--> Worker Fleet
         - Ingestion Worker
         - Narrative Worker
         - TTS Worker
         - Assembly Worker
         - QA Worker
         - Packaging Worker
```

## 1.7 Service Responsibilities
### Ingestion Service
- Import manuscript files
- Normalize text
- Detect chapters
- Preserve canonical manuscript representation

### Narrative Service
- Detect scenes
- Detect dialogue blocks
- Attribute speaker candidates
- Extract character registry
- Generate confidence scores

### Casting Service
- Manage narrator and character voice profiles
- Assign characters to voices
- Persist voice bible
- Manage pronunciation dictionary

### Direction Service
- Compute scene mood defaults
- Compute line-level delivery directives
- Control pauses, energy, pacing, and style

### TTS Service
- Generate per-segment speech audio
- Support multiple model backends
- Emit timing/alignment data
- Store render artifacts

### Audio Assembly Service
- Insert silence and transitions
- Assemble segment renders into chapter stems
- Layer ambience/SFX conservatively
- Output chapter mix and stems

### QA Service
- Detect missing renders
- Check clipping/loudness
- Flag pronunciation anomalies
- Detect probable voice drift and attribution issues

### Review Service
- Store comments/issues
- Track review states
- Track patch history

### Export Service
- Build WAV/MP3/M4B outputs
- Attach metadata
- Package chaptered audiobook output

### Rights Service (minimal in MVP)
- Store rights declaration
- Gate export on explicit user acknowledgment

## 1.8 Processing Pipeline
```text
1. Import source
2. Normalize manuscript
3. Split chapters
4. Split scenes
5. Extract segments
6. Build character registry
7. Assign speaker candidates
8. Assign voice profiles
9. Apply pronunciation rules
10. Apply direction rules
11. Generate segment audio
12. Assemble speech stem
13. Layer ambience (optional)
14. Run QA checks
15. Review and patch
16. Export final package
```

## 1.9 Data Flow by Stage
### Stage A — Ingestion
Input: manuscript file  
Output: canonical manuscript JSON + chapter list

### Stage B — Narrative Structuring
Input: canonical manuscript  
Output: scene list + segment list + character registry + attribution confidence

### Stage C — Casting & Direction
Input: character registry + user voice choices  
Output: render directives per segment

### Stage D — Generation
Input: segment + voice profile + direction + pronunciation rules  
Output: speech audio + diagnostics + alignment data

### Stage E — Assembly & QA
Input: segment renders  
Output: chapter stems + mixed output + quality report

### Stage F — Review & Export
Input: reviewed chapter output  
Output: packaged audiobook files

## 1.10 Failure Handling Strategy
- Every long-running operation is a **job**.
- Each job must write progress and status.
- Each stage must be rerunnable.
- Partial outputs must not corrupt prior valid artifacts.
- Regeneration should only invalidate downstream derived artifacts for the affected scope.

## 1.11 Caching Strategy
Cache generated segment renders using a deterministic key derived from:
- normalized segment text
- voice profile configuration
- direction settings
- pronunciation dictionary version
- backend and model version

This minimizes repeat inference during patching.

## 1.12 Security and Privacy
### MVP
- Local storage by default
- No silent cloud upload
- Explicit rights confirmation before export

### Later
- RBAC
- audit logs
- tenant isolation
- signed rights evidence
- voice consent records

## 1.13 Operational Decisions
- SQLite for local MVP
- Postgres for hosted scale-up
- filesystem artifacts for local MVP
- object storage for hosted platform
- REST APIs for MVP
- async jobs for expensive operations
- structured logs and debug bundles from day one

## 1.14 Architecture Decisions Record (initial)
### ADR-001: Segment is the atomic unit
**Decision**: Use `Segment` as the smallest renderable/editable unit.  
**Reason**: Enables patchability and high-quality review workflows.

### ADR-002: Use manifest-driven pipeline
**Decision**: Every pipeline stage reads/writes manifests.  
**Reason**: Improves resumability, debugging, and reproducibility.

### ADR-003: Local-first MVP
**Decision**: Build single-node runtime first.  
**Reason**: Minimizes operational complexity and validates product value faster.

### ADR-004: Abstract TTS backends
**Decision**: Use adapter layer for synthesis.  
**Reason**: Prevents lock-in to one runtime.

---

# 2) DOMAIN_MODEL.md

## 2.1 Overview
This document defines the domain entities, relationships, state transitions, and lifecycle rules for the AI Audiobook Studio MVP.

## 2.2 Core Domain Hierarchy
```text
Project
├─ SourceDocument
├─ Chapter
│  ├─ Scene
│  │  ├─ Segment
│  │  └─ SceneDirective
│  ├─ ChapterRender
│  └─ QualityReport
├─ Character
├─ VoiceProfile
├─ PronunciationEntry
├─ Issue
├─ Comment
├─ ExportPackage
└─ RightsDeclaration
```

## 2.3 Entity Definitions

### Project
Represents the top-level audiobook production workspace.

**Fields**
- id
- title
- author
- description
- rights_status
- status
- settings
- created_at
- updated_at

**Lifecycle States**
- `draft`
- `structured`
- `cast_configured`
- `generating`
- `reviewing`
- `ready_for_export`
- `exported`
- `archived`

**Rules**
- Cannot export if rights declaration is missing.
- Moves to `structured` only after successful chapter/scene/segment generation.

### SourceDocument
Stores information about the imported manuscript.

**Fields**
- id
- project_id
- original_path
- normalized_text_path
- checksum
- parser_version
- word_count

### Chapter
Represents a major content division.

**Fields**
- id
- project_id
- chapter_number
- title
- order_index
- word_count
- status

**Lifecycle States**
- `pending`
- `structured`
- `ready_for_generation`
- `generating`
- `generated`
- `needs_review`
- `approved`
- `exported`

### Scene
Represents a meaningful scene unit within a chapter.

**Fields**
- id
- chapter_id
- order_index
- title
- mood_tags
- style_preset
- ambience_profile
- start_offset
- end_offset

### Segment
Represents the smallest renderable/editable unit.

**Fields**
- id
- scene_id
- order_index
- segment_type
- speaker_character_id
- text_content
- normalized_text
- attribution_confidence
- direction
- duration_ms
- status
- current_render_id

**Segment Types**
- `narration`
- `dialogue`
- `monologue`
- `silence`
- `ambience_cue`
- `sfx_cue`

**Lifecycle States**
- `pending`
- `ready`
- `generating`
- `generated`
- `qa_flagged`
- `needs_review`
- `approved`
- `superseded`

**Rules**
- Only one `current_render_id` is active at a time.
- Regenerating a segment creates a new render; it does not overwrite history.

### Character
Represents a distinct story character or speaker role.

**Fields**
- id
- project_id
- display_name
- aliases
- description
- role_type
- notes

**Role Types**
- `narrator`
- `major`
- `minor`
- `ambient_voice`
- `unknown`

### VoiceProfile
Represents a reusable voice configuration.

**Fields**
- id
- project_id
- name
- backend
- base_voice_id
- style_prompt
- settings
- sample_audio_path
- is_narrator_default

**Rules**
- Multiple characters may share a voice in MVP if needed.
- Exactly zero or one narrator default per project.

### CharacterVoiceAssignment
Maps characters to voice profiles.

**Fields**
- id
- project_id
- character_id
- voice_profile_id

### PronunciationEntry
Overrides pronunciation behavior for terms/names.

**Fields**
- id
- project_id
- term
- phonetic
- replacement_text
- notes

### SegmentRender
Represents an immutable audio generation output for a segment.

**Fields**
- id
- segment_id
- voice_profile_id
- backend
- backend_model_version
- render_params
- speech_audio_path
- alignment_json_path
- waveform_json_path
- duration_ms
- qa_summary
- created_at

**Rules**
- Segment renders are append-only.
- The segment points to the active render via `current_render_id`.

### ChapterRender
Represents an assembled chapter output.

**Fields**
- id
- chapter_id
- render_mode
- speech_stem_path
- ambience_stem_path
- mixed_audio_path
- manifest_path
- duration_ms
- status

### Issue
Tracks QA or editorial issues.

**Fields**
- id
- project_id
- chapter_id
- scene_id
- segment_id
- severity
- category
- title
- description
- status
- metadata

**Severities**
- `info`
- `warning`
- `error`
- `blocking`

**Categories**
- `pronunciation`
- `attribution`
- `clipping`
- `loudness`
- `missing_audio`
- `voice_drift`
- `timing`
- `editorial`

### Comment
Anchored human feedback.

**Fields**
- id
- project_id
- chapter_id
- segment_id
- body
- created_by
- created_at

### ExportPackage
Represents an export artifact.

**Fields**
- id
- project_id
- format
- scope
- metadata
- output_path
- status

### RightsDeclaration
Stores the user’s rights assertion.

**Fields**
- id
- project_id
- declaration_type
- status
- evidence_path
- notes

## 2.4 Relationships
- A `Project` has one `SourceDocument`.
- A `Project` has many `Chapters`.
- A `Chapter` has many `Scenes`.
- A `Scene` has many `Segments`.
- A `Project` has many `Characters`.
- A `Project` has many `VoiceProfiles`.
- A `Character` may have one active `VoiceProfile` assignment.
- A `Segment` may reference one `Character` as speaker.
- A `Segment` has many `SegmentRenders`.
- A `Chapter` has many `ChapterRenders`.
- A `Project` has many `Issues`, `Comments`, and `Exports`.

## 2.5 Lifecycle Rules
### Project Lifecycle
1. create project
2. import source
3. structure content
4. configure cast
5. generate chapters
6. review issues
7. export outputs

### Segment Lifecycle
1. segment created
2. direction applied
3. render requested
4. render stored
5. QA flags checked
6. segment approved or regenerated

### Chapter Lifecycle
1. chapter structured
2. segment renders generated
3. chapter stems assembled
4. QA executed
5. issues reviewed
6. chapter approved
7. exportable

## 2.6 Invariants
- `order_index` must be unique within chapter/scene scope.
- A segment cannot be `approved` without a valid render.
- A chapter cannot be `approved` while containing blocking issues.
- Export requires at least one approved chapter render.
- Active render history must remain traceable.

## 2.7 Domain Events
Recommended internal events:
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

---

# 3) API_SPEC.yaml

```yaml
openapi: 3.1.0
info:
  title: AI Audiobook Studio API
  version: 0.1.0
  description: Local-first MVP API for audiobook project creation, structure management, voice assignment, rendering, review, and export.
servers:
  - url: http://localhost:8000
paths:
  /api/v1/projects:
    get:
      summary: List projects
      responses:
        '200':
          description: Project list
    post:
      summary: Create project
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProjectRequest'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Project'

  /api/v1/projects/{projectId}:
    get:
      summary: Get project
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Project detail
    patch:
      summary: Update project
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateProjectRequest'
      responses:
        '200':
          description: Updated
    delete:
      summary: Delete project
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '204':
          description: Deleted

  /api/v1/projects/{projectId}/source/import:
    post:
      summary: Import manuscript source
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
      responses:
        '202':
          description: Import job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/projects/{projectId}/source/reparse:
    post:
      summary: Re-run parsing on source document
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '202':
          description: Reparse job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/projects/{projectId}/chapters:
    get:
      summary: List chapters for project
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Chapter list

  /api/v1/chapters/{chapterId}:
    get:
      summary: Get chapter detail
      parameters:
        - $ref: '#/components/parameters/ChapterId'
      responses:
        '200':
          description: Chapter detail

  /api/v1/chapters/{chapterId}/scenes:
    get:
      summary: List scenes for chapter
      parameters:
        - $ref: '#/components/parameters/ChapterId'
      responses:
        '200':
          description: Scene list

  /api/v1/scenes/{sceneId}/segments:
    get:
      summary: List segments for scene
      parameters:
        - $ref: '#/components/parameters/SceneId'
      responses:
        '200':
          description: Segment list

  /api/v1/segments/{segmentId}:
    patch:
      summary: Update segment text or direction
      parameters:
        - $ref: '#/components/parameters/SegmentId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateSegmentRequest'
      responses:
        '200':
          description: Updated segment

  /api/v1/projects/{projectId}/characters:
    get:
      summary: List characters
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Character list
    post:
      summary: Create character
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCharacterRequest'
      responses:
        '201':
          description: Character created

  /api/v1/characters/{characterId}:
    patch:
      summary: Update character
      parameters:
        - $ref: '#/components/parameters/CharacterId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateCharacterRequest'
      responses:
        '200':
          description: Character updated

  /api/v1/projects/{projectId}/voices:
    get:
      summary: List voice profiles
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Voice list
    post:
      summary: Create voice profile
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateVoiceProfileRequest'
      responses:
        '201':
          description: Voice profile created

  /api/v1/voices/{voiceId}:
    patch:
      summary: Update voice profile
      parameters:
        - $ref: '#/components/parameters/VoiceId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateVoiceProfileRequest'
      responses:
        '200':
          description: Voice updated

  /api/v1/voices/{voiceId}/preview:
    post:
      summary: Generate a voice preview clip
      parameters:
        - $ref: '#/components/parameters/VoiceId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/VoicePreviewRequest'
      responses:
        '202':
          description: Preview job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/characters/{characterId}/assign-voice:
    post:
      summary: Assign voice to character
      parameters:
        - $ref: '#/components/parameters/CharacterId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AssignVoiceRequest'
      responses:
        '200':
          description: Voice assigned

  /api/v1/projects/{projectId}/pronunciations:
    get:
      summary: List pronunciation entries
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Pronunciation list
    post:
      summary: Create pronunciation entry
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreatePronunciationEntryRequest'
      responses:
        '201':
          description: Created

  /api/v1/pronunciations/{entryId}:
    patch:
      summary: Update pronunciation entry
      parameters:
        - $ref: '#/components/parameters/PronunciationEntryId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdatePronunciationEntryRequest'
      responses:
        '200':
          description: Updated
    delete:
      summary: Delete pronunciation entry
      parameters:
        - $ref: '#/components/parameters/PronunciationEntryId'
      responses:
        '204':
          description: Deleted

  /api/v1/projects/{projectId}/generate/chapters:
    post:
      summary: Generate all or selected chapters
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GenerateChaptersRequest'
      responses:
        '202':
          description: Generation job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/chapters/{chapterId}/generate:
    post:
      summary: Generate a chapter
      parameters:
        - $ref: '#/components/parameters/ChapterId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GenerateChapterRequest'
      responses:
        '202':
          description: Generation job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/segments/{segmentId}/generate:
    post:
      summary: Generate or regenerate one segment
      parameters:
        - $ref: '#/components/parameters/SegmentId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/GenerateSegmentRequest'
      responses:
        '202':
          description: Segment generation job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/jobs/{jobId}:
    get:
      summary: Get job status
      parameters:
        - $ref: '#/components/parameters/JobId'
      responses:
        '200':
          description: Job status detail
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobStatus'

  /api/v1/jobs/{jobId}/cancel:
    post:
      summary: Cancel job
      parameters:
        - $ref: '#/components/parameters/JobId'
      responses:
        '200':
          description: Job cancellation result

  /api/v1/projects/{projectId}/issues:
    get:
      summary: List project issues
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Issue list

  /api/v1/issues/{issueId}:
    patch:
      summary: Update issue state
      parameters:
        - $ref: '#/components/parameters/IssueId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateIssueRequest'
      responses:
        '200':
          description: Updated issue

  /api/v1/segments/{segmentId}/comments:
    post:
      summary: Add comment on segment
      parameters:
        - $ref: '#/components/parameters/SegmentId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCommentRequest'
      responses:
        '201':
          description: Comment created

  /api/v1/segments/{segmentId}/mark-reviewed:
    post:
      summary: Mark segment as reviewed
      parameters:
        - $ref: '#/components/parameters/SegmentId'
      responses:
        '200':
          description: Segment marked reviewed

  /api/v1/projects/{projectId}/exports:
    get:
      summary: List exports
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Export list
    post:
      summary: Create export
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateExportRequest'
      responses:
        '202':
          description: Export job accepted
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobAcceptedResponse'

  /api/v1/exports/{exportId}:
    get:
      summary: Get export detail
      parameters:
        - $ref: '#/components/parameters/ExportId'
      responses:
        '200':
          description: Export detail

  /api/v1/projects/{projectId}/rights:
    get:
      summary: Get rights declarations
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      responses:
        '200':
          description: Rights detail

  /api/v1/projects/{projectId}/rights/declaration:
    post:
      summary: Create or update rights declaration
      parameters:
        - $ref: '#/components/parameters/ProjectId'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpsertRightsDeclarationRequest'
      responses:
        '200':
          description: Rights declaration stored

components:
  parameters:
    ProjectId:
      name: projectId
      in: path
      required: true
      schema:
        type: string
    ChapterId:
      name: chapterId
      in: path
      required: true
      schema:
        type: string
    SceneId:
      name: sceneId
      in: path
      required: true
      schema:
        type: string
    SegmentId:
      name: segmentId
      in: path
      required: true
      schema:
        type: string
    CharacterId:
      name: characterId
      in: path
      required: true
      schema:
        type: string
    VoiceId:
      name: voiceId
      in: path
      required: true
      schema:
        type: string
    PronunciationEntryId:
      name: entryId
      in: path
      required: true
      schema:
        type: string
    JobId:
      name: jobId
      in: path
      required: true
      schema:
        type: string
    IssueId:
      name: issueId
      in: path
      required: true
      schema:
        type: string
    ExportId:
      name: exportId
      in: path
      required: true
      schema:
        type: string
  schemas:
    Project:
      type: object
      properties:
        id:
          type: string
        title:
          type: string
        author:
          type: string
        rightsStatus:
          type: string
        status:
          type: string
        createdAt:
          type: string
          format: date-time
        updatedAt:
          type: string
          format: date-time
    CreateProjectRequest:
      type: object
      required: [title, rightsStatus]
      properties:
        title:
          type: string
        author:
          type: string
        description:
          type: string
        rightsStatus:
          type: string
        settings:
          type: object
          additionalProperties: true
    UpdateProjectRequest:
      type: object
      properties:
        title:
          type: string
        author:
          type: string
        description:
          type: string
        status:
          type: string
        settings:
          type: object
          additionalProperties: true
    CreateCharacterRequest:
      type: object
      required: [displayName]
      properties:
        displayName:
          type: string
        aliases:
          type: array
          items:
            type: string
        description:
          type: string
        roleType:
          type: string
    UpdateCharacterRequest:
      type: object
      properties:
        displayName:
          type: string
        aliases:
          type: array
          items:
            type: string
        description:
          type: string
        roleType:
          type: string
        notes:
          type: string
    CreateVoiceProfileRequest:
      type: object
      required: [name, backend]
      properties:
        name:
          type: string
        backend:
          type: string
        baseVoiceId:
          type: string
        stylePrompt:
          type: string
        settings:
          type: object
          additionalProperties: true
        isNarratorDefault:
          type: boolean
    UpdateVoiceProfileRequest:
      type: object
      properties:
        name:
          type: string
        stylePrompt:
          type: string
        settings:
          type: object
          additionalProperties: true
        isNarratorDefault:
          type: boolean
    VoicePreviewRequest:
      type: object
      required: [text]
      properties:
        text:
          type: string
        stylePrompt:
          type: string
    AssignVoiceRequest:
      type: object
      required: [voiceProfileId]
      properties:
        voiceProfileId:
          type: string
    CreatePronunciationEntryRequest:
      type: object
      required: [term]
      properties:
        term:
          type: string
        phonetic:
          type: string
        replacementText:
          type: string
        notes:
          type: string
    UpdatePronunciationEntryRequest:
      type: object
      properties:
        phonetic:
          type: string
        replacementText:
          type: string
        notes:
          type: string
    UpdateSegmentRequest:
      type: object
      properties:
        textContent:
          type: string
        speakerCharacterId:
          type: string
        direction:
          type: object
          additionalProperties: true
    GenerateChaptersRequest:
      type: object
      properties:
        chapterIds:
          type: array
          items:
            type: string
        renderMode:
          type: string
        qualityMode:
          type: string
        includeAmbience:
          type: boolean
        regenerateOnlyFailed:
          type: boolean
    GenerateChapterRequest:
      type: object
      properties:
        renderMode:
          type: string
        qualityMode:
          type: string
        includeAmbience:
          type: boolean
        regenerateOnlyFailed:
          type: boolean
    GenerateSegmentRequest:
      type: object
      properties:
        voiceProfileId:
          type: string
        directionOverride:
          type: object
          additionalProperties: true
        force:
          type: boolean
    UpdateIssueRequest:
      type: object
      properties:
        status:
          type: string
        severity:
          type: string
        description:
          type: string
    CreateCommentRequest:
      type: object
      required: [body]
      properties:
        body:
          type: string
    CreateExportRequest:
      type: object
      required: [format, scope]
      properties:
        format:
          type: string
        scope:
          type: string
        metadata:
          type: object
          additionalProperties: true
    UpsertRightsDeclarationRequest:
      type: object
      required: [declarationType, status]
      properties:
        declarationType:
          type: string
        status:
          type: string
        notes:
          type: string
        evidencePath:
          type: string
    JobAcceptedResponse:
      type: object
      properties:
        jobId:
          type: string
        status:
          type: string
        pollUrl:
          type: string
    JobStatus:
      type: object
      properties:
        id:
          type: string
        jobType:
          type: string
        status:
          type: string
        progress:
          type: object
          additionalProperties: true
        errorMessage:
          type: string
```

---

# 4) DB_SCHEMA.md

## 4.1 Database Strategy
### MVP
- Engine: SQLite
- ORM: SQLAlchemy
- Migrations: Alembic

### Scaled Version
- Engine: Postgres
- ORM models largely unchanged

## 4.2 Design Principles
- Keep relational metadata normalized.
- Keep audio blobs out of the DB.
- Use append-only render history.
- Favor explicit status columns over inferred state.

## 4.3 Core Tables

### `projects`
Purpose: top-level project metadata.

Key columns:
- `id` TEXT PK
- `title` TEXT NOT NULL
- `author` TEXT
- `description` TEXT
- `rights_status` TEXT NOT NULL
- `status` TEXT NOT NULL
- `settings_json` TEXT
- `created_at`, `updated_at`

Indexes:
- index on `status`
- index on `updated_at`

### `source_documents`
Purpose: link source manuscript artifacts to a project.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `original_path` TEXT
- `normalized_text_path` TEXT
- `checksum` TEXT
- `word_count` INTEGER
- `parser_version` TEXT

### `chapters`
Purpose: chapter-level metadata and status.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `chapter_number` INTEGER
- `title` TEXT
- `order_index` INTEGER NOT NULL
- `source_text_path` TEXT
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
Purpose: story speaker registry.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `display_name` TEXT NOT NULL
- `aliases_json` TEXT
- `description` TEXT
- `role_type` TEXT
- `notes` TEXT

Indexes:
- index on `(project_id, display_name)`

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
- index on `(project_id, term)`

### `segments`
Purpose: atomic generation/review unit.

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
- index on `speaker_character_id`
- index on `status`

### `segment_renders`
Purpose: immutable segment audio render history.

Key columns:
- `id` TEXT PK
- `segment_id` FK
- `voice_profile_id` FK
- `backend` TEXT NOT NULL
- `backend_model_version` TEXT
- `render_params_json` TEXT
- `speech_audio_path` TEXT
- `alignment_json_path` TEXT
- `waveform_json_path` TEXT
- `duration_ms` INTEGER
- `qa_summary_json` TEXT
- `created_at` DATETIME

Indexes:
- index on `(segment_id, created_at)`

### `chapter_renders`
Purpose: assembled chapter outputs.

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

Indexes:
- index on `(chapter_id, created_at)`

### `issues`
Purpose: QA/editorial findings.

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
- index on `(project_id, status)`
- index on `(project_id, severity)`

### `comments`
Purpose: human comments anchored to project items.

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
- `created_at`, `started_at`, `finished_at`

Indexes:
- index on `(project_id, status)`
- index on `job_type`

### `rights_declarations`
Purpose: rights assertion and export gating.

Key columns:
- `id` TEXT PK
- `project_id` FK
- `declaration_type` TEXT NOT NULL
- `status` TEXT NOT NULL
- `evidence_path` TEXT
- `notes` TEXT
- `created_at`, `updated_at`

## 4.4 Migration Order
Recommended initial migration order:
1. projects
2. source_documents
3. chapters
4. scenes
5. characters
6. voice_profiles
7. character_voice_assignments
8. pronunciation_entries
9. segments
10. segment_renders
11. chapter_renders
12. issues
13. comments
14. exports
15. jobs
16. rights_declarations

## 4.5 Lifecycle Semantics
- `segments.current_render_id` references the active render.
- Regeneration inserts a new row into `segment_renders`.
- Any affected chapter render becomes stale after segment regeneration.
- Export always points to a specific render package.

## 4.6 Schema Evolution for Hosted Platform
Add later:
- organizations
- users
- memberships
- audit_logs
- api_keys
- asset_permissions
- review_assignments
- billing_accounts

---

# 5) PIPELINE_MANIFEST_SPEC.md

## 5.1 Purpose
Pipeline manifests make each stage resumable, inspectable, and reproducible. Every pipeline stage consumes a manifest and emits a manifest.

## 5.2 Principles
- JSON format for simplicity
- version every manifest schema
- include content hashes where practical
- reference artifacts by path/URI
- include stage status and diagnostics

## 5.3 Manifest Types
1. `source_manifest.json`
2. `structure_manifest.json`
3. `casting_manifest.json`
4. `direction_manifest.json`
5. `segment_render_manifest.json`
6. `chapter_assembly_manifest.json`
7. `qa_manifest.json`
8. `export_manifest.json`

## 5.4 Common Envelope
Every manifest should include:
```json
{
  "manifestType": "structure_manifest",
  "schemaVersion": "0.1.0",
  "projectId": "proj_001",
  "chapterId": "chap_001",
  "generatedAt": "2026-03-17T12:00:00Z",
  "generator": {
    "service": "narrative-service",
    "version": "0.1.0"
  },
  "status": "completed",
  "diagnostics": [],
  "payload": {}
}
```

## 5.5 Source Manifest
Purpose: record ingestion output.

Payload fields:
- source document metadata
- normalized text artifact path
- chapter boundary hints
- parser warnings
- checksum

Example payload:
```json
{
  "sourceDocumentId": "src_001",
  "originalPath": "/projects/proj_001/source/book.epub",
  "normalizedTextPath": "/projects/proj_001/source/normalized.txt",
  "checksum": "abc123",
  "parserVersion": "ingestion-0.1.0",
  "wordCount": 105432,
  "chapterHints": [
    {"title": "Chapter 1", "offset": 0},
    {"title": "Chapter 2", "offset": 9342}
  ],
  "warnings": []
}
```

## 5.6 Structure Manifest
Purpose: record chapter/scene/segment structure.

Payload fields:
- character candidates
- scene list
- segment list
- speaker attribution confidence

Example payload:
```json
{
  "chapterId": "chap_001",
  "scenes": [
    {
      "sceneId": "scene_001",
      "orderIndex": 0,
      "moodTags": ["tense", "mysterious"],
      "segments": [
        {
          "segmentId": "seg_001",
          "segmentType": "narration",
          "speakerCharacterId": null,
          "text": "I woke up confused.",
          "attributionConfidence": 1.0
        }
      ]
    }
  ],
  "characterCandidates": [
    {"name": "Grace", "aliases": ["Ryland"]}
  ]
}
```

## 5.7 Casting Manifest
Purpose: record narrator and character voice assignments.

Payload fields:
- narrator voice profile
- character voice assignments
- pronunciation dictionary version

Example payload:
```json
{
  "narratorVoiceProfileId": "voice_narrator_01",
  "characterAssignments": [
    {"characterId": "char_grace", "voiceProfileId": "voice_01"},
    {"characterId": "char_rocky", "voiceProfileId": "voice_02"}
  ],
  "pronunciationDictionaryVersion": "lex_3"
}
```

## 5.8 Direction Manifest
Purpose: record computed delivery directives.

Payload fields:
- per-scene defaults
- per-segment overrides
- pacing/pause settings
- ambience suggestion hints

Example payload:
```json
{
  "chapterId": "chap_001",
  "sceneDefaults": [
    {
      "sceneId": "scene_001",
      "stylePreset": "expressive",
      "pace": "medium",
      "ambienceProfile": "spaceship_roomtone"
    }
  ],
  "segmentOverrides": [
    {
      "segmentId": "seg_004",
      "delivery": "urgent",
      "pauseBeforeMs": 200,
      "pauseAfterMs": 350
    }
  ]
}
```

## 5.9 Segment Render Manifest
Purpose: record a single segment generation output.

Payload fields:
- render request config
- audio artifact paths
- alignment path
- diagnostics

Example payload:
```json
{
  "segmentId": "seg_004",
  "renderId": "rend_009",
  "voiceProfileId": "voice_02",
  "backend": "qwen",
  "backendModelVersion": "qwen-tts-local-0.1",
  "renderKey": "hash_123",
  "speechAudioPath": "/projects/proj_001/chapters/chap_001/segments/seg_004/render_v2.wav",
  "alignmentJsonPath": "/projects/proj_001/chapters/chap_001/segments/seg_004/alignment_v2.json",
  "durationMs": 1850,
  "diagnostics": []
}
```

## 5.10 Chapter Assembly Manifest
Purpose: record assembly of chapter-level stems and mix.

Payload fields:
- ordered segment render list
- inserted pauses
- ambience asset references
- output stem and mix paths

Example payload:
```json
{
  "chapterId": "chap_001",
  "renderMode": "light_cinematic",
  "orderedRenders": [
    {"segmentId": "seg_001", "renderId": "rend_001"},
    {"segmentId": "seg_002", "renderId": "rend_002"}
  ],
  "speechStemPath": "/projects/proj_001/chapters/chap_001/stems/speech.wav",
  "ambienceStemPath": "/projects/proj_001/chapters/chap_001/stems/ambience.wav",
  "mixedAudioPath": "/projects/proj_001/chapters/chap_001/mixes/mixed_v1.wav",
  "durationMs": 432000
}
```

## 5.11 QA Manifest
Purpose: summarize automated QA findings.

Payload fields:
- issue summary
- warnings/errors
- objective checks
- pass/fail

Example payload:
```json
{
  "chapterId": "chap_001",
  "checks": [
    {"name": "missing_segments", "status": "pass"},
    {"name": "clipping", "status": "warning", "count": 2},
    {"name": "pronunciation_anomalies", "status": "warning", "count": 1}
  ],
  "blocking": false,
  "issueIds": ["issue_1002", "issue_1003"]
}
```

## 5.12 Export Manifest
Purpose: describe final export package.

Payload fields:
- export format
- source chapter renders
- metadata used
- output file paths

Example payload:
```json
{
  "exportId": "exp_001",
  "format": "m4b",
  "scope": "full_project",
  "chapters": [
    {"chapterId": "chap_001", "chapterRenderId": "chaprend_001"}
  ],
  "metadata": {
    "title": "Sample Book",
    "author": "Sample Author"
  },
  "outputPath": "/projects/proj_001/exports/book_v1.m4b"
}
```

## 5.13 Manifest Validation Rules
- `manifestType` required
- `schemaVersion` required
- `projectId` required
- `payload` required
- referenced artifacts must exist before stage is considered complete
- diagnostics must not be silently discarded

---

# 6) VOICE_BIBLE_SPEC.md

## 6.1 Purpose
The voice bible ensures long-form voice consistency for narrator and characters. It is the source of truth for casting decisions and pronunciation behavior.

## 6.2 Principles
- Consistency matters more than novelty.
- Voice assignments should be explicit and durable.
- Narrator identity must remain stable across the title.
- Character variation should be recognizable but not cartoonish.

## 6.3 Voice Bible Structure
A voice bible is a project-level artifact composed of:
- narrator profile
- character profiles
- pronunciation dictionary
- style and intensity rules
- do-not-cross rules

## 6.4 Narrator Profile
Fields:
- `voiceProfileId`
- `name`
- `role`
- `toneKeywords`
- `pacingDefault`
- `energyDefault`
- `warmth`
- `clarity`
- `accentNotes`
- `stylePrompt`
- `doNotOverdo`

Example:
```json
{
  "voiceProfileId": "voice_narrator_01",
  "name": "Narrator Main",
  "role": "narrator",
  "toneKeywords": ["warm", "intelligent", "steady"],
  "pacingDefault": "medium",
  "energyDefault": "restrained",
  "warmth": 0.7,
  "clarity": 0.9,
  "accentNotes": "neutral international English",
  "stylePrompt": "warm, confident, clear, emotionally restrained",
  "doNotOverdo": ["melodrama", "sudden shouting", "overly theatrical pauses"]
}
```

## 6.5 Character Profile
Fields:
- `characterId`
- `displayName`
- `aliases`
- `voiceProfileId`
- `characterSummary`
- `vocalIdentity`
- `deliveryDefaults`
- `emotionalRange`
- `accentNotes`
- `speechQuirks`
- `relationshipToNarrator`
- `usageRules`

Example:
```json
{
  "characterId": "char_rocky",
  "displayName": "Rocky",
  "aliases": ["Eridian"],
  "voiceProfileId": "voice_rocky_01",
  "characterSummary": "non-human but deeply expressive, brilliant, curious",
  "vocalIdentity": {
    "pitch": "low",
    "texture": "textured but intelligible",
    "cadence": "measured"
  },
  "deliveryDefaults": {
    "pace": "medium_slow",
    "energy": "calm",
    "expressiveness": "controlled"
  },
  "emotionalRange": ["curious", "concerned", "playful", "serious"],
  "accentNotes": "non-human stylization, intelligibility prioritized",
  "speechQuirks": ["precise phrasing"],
  "relationshipToNarrator": "should contrast clearly with narrator voice",
  "usageRules": {
    "avoidCaricature": true,
    "keepRecognitionStable": true
  }
}
```

## 6.6 Pronunciation Dictionary
Fields:
- `term`
- `phonetic`
- `replacementText`
- `appliesToCharacters`
- `notes`

## 6.7 Style and Intensity Rules
The voice bible should define global moderation rules.

Suggested fields:
- `maxExpressiveness`
- `allowWhispering`
- `allowShouting`
- `pauseStyle`
- `dialogueSeparationGoal`
- `narrationRestraint`

## 6.8 Do-Not-Cross Rules
Examples:
- narrator voice must never be assigned to non-narrator characters unless explicitly approved
- comedic characters must not break tonal consistency of serious scenes
- minor characters may share supporting voices, but major characters must be distinct if possible
- no scene should exceed defined ambience intensity threshold by default

## 6.9 Voice Bible File Example
```json
{
  "schemaVersion": "0.1.0",
  "projectId": "proj_001",
  "narrator": {
    "voiceProfileId": "voice_narrator_01",
    "name": "Narrator Main"
  },
  "characters": [],
  "pronunciations": [],
  "globalRules": {
    "maxExpressiveness": "medium",
    "allowWhispering": true,
    "allowShouting": false,
    "narrationRestraint": "high"
  }
}
```

## 6.10 Workflow Rules
- build voice bible before full chapter generation
- any narrator change invalidates all chapters unless explicitly versioned as a new project branch
- character voice changes mark affected segment renders as stale
- pronunciation edits invalidate only segments containing impacted terms

---

# 7) QA_RULEBOOK.md

## 7.1 Purpose
This document defines the automated and human review standards for the MVP.

The quality goal is not “perfect human studio audio.” The goal is a **trustworthy, immersive, patchable premium draft**.

## 7.2 QA Layers
1. **Automated technical QA**
2. **Automated linguistic/content QA**
3. **Human editorial QA**
4. **Human listening QA**

## 7.3 Automated Technical Checks
### Required Checks
- missing segment render detection
- file existence validation
- zero-duration render detection
- clipping detection
- abnormal silence detection
- chapter loudness bounds
- corrupted export detection

### Rules
- Any missing segment render is `blocking`.
- Any unreadable audio file is `blocking`.
- Clipping above threshold is at least `warning` and may escalate.
- Extreme silence anomalies must be flagged.

## 7.4 Automated Linguistic Checks
### Required Checks
- pronunciation dictionary coverage hits/misses
- repeated word anomaly detection
- obvious text truncation detection
- probable attribution mismatch detection
- unsupported character symbol detection

### Rules
- suspected truncation is `blocking`.
- repeated word anomalies are `warning`.
- attribution mismatch is `warning` or `error` depending on confidence.

## 7.5 Automated Narrative Checks
### Recommended Checks
- narrator vs character voice confusion
- sudden style drift within a scene
- ambience masking speech threshold violations
- chapter render completeness

## 7.6 Human Editorial QA Checklist
For each reviewed chapter, ask:
1. Are all lines present?
2. Are major character voices distinguishable?
3. Does narration feel stable and consistent?
4. Are pronunciations acceptable?
5. Are emotional cues appropriate to the scene?
6. Is any line unintentionally funny, robotic, or melodramatic?
7. Is ambience too loud, too obvious, or distracting?
8. Are pauses natural?
9. Does the chapter feel coherent end-to-end?
10. Which lines require regeneration?

## 7.7 Human Listening QA Rubric
Rate each area from 1–5.

### A. Intelligibility
- Can every line be understood easily?

### B. Voice Consistency
- Does each major voice remain stable across the chapter?

### C. Character Separation
- Are important speakers distinguishable?

### D. Emotional Appropriateness
- Does delivery fit the scene without overacting?

### E. Narrative Flow
- Does chapter pacing feel natural?

### F. Production Restraint
- Are ambience and SFX tasteful rather than intrusive?

### G. Overall Immersion
- Would a listener prefer this over generic single-voice TTS?

## 7.8 Severity Definitions
### Info
Minor note. No immediate action required.

### Warning
Issue should be reviewed; export may still be acceptable.

### Error
Issue materially hurts quality and should normally be fixed.

### Blocking
Issue prevents chapter approval or export.

## 7.9 Issue Categories
- pronunciation
- attribution
- clipping
- loudness
- missing_audio
- voice_drift
- timing
- ambience_masking
- editorial
- truncation

## 7.10 Approval Rules
### Segment Approval
A segment may be approved if:
- audio exists,
- no blocking issue exists,
- it passes human or automated approval rules,
- it is judged acceptable in context.

### Chapter Approval
A chapter may be approved if:
- all segments have active renders,
- no blocking issue remains,
- chapter-level QA passed,
- any warnings are consciously accepted.

### Export Approval
A project may be exported if:
- rights declaration exists,
- each included chapter has approved chapter render,
- no project-level blocking issue remains.

## 7.11 Regression QA
Whenever any of the following changes occur, rerun targeted QA:
- pronunciation dictionary update
- voice profile update
- narrator change
- segment regeneration
- chapter reassembly
- export packaging change

## 7.12 Acceptance Thresholds for MVP
The MVP is quality-acceptable when:
- users can identify major characters reliably,
- narration stays stable across a chapter,
- obvious technical defects are rare and patchable,
- ambience remains subtle,
- listeners rate immersion above generic TTS.

---

# 8) MVP_EXECUTION_PLAN.md

## 8.1 Goal
Ship a usable local-first MVP that allows a user to:
- create project,
- import manuscript,
- structure it into chapters/scenes/segments,
- assign narrator and character voices,
- generate a chapter,
- selectively regenerate bad lines,
- export chaptered audio.

## 8.2 Team Assumption
Ideal tiny-team configuration:
- 1 full-stack/backend engineer
- 1 ML/audio engineer
- optional design support

If solo, sequence remains the same but timelines expand.

## 8.3 Sprint Structure
Assume 2-week sprints.

---

## Sprint 0 — Foundations
### Goals
- establish repo, baseline tooling, and local runtime

### Tasks
- initialize monorepo
- bootstrap FastAPI app
- bootstrap Next.js app
- set up SQLite + Alembic
- create domain model package
- define local artifact directory layout
- add structured logging
- add job runner skeleton
- create sample seed project script

### Deliverables
- working backend server
- working frontend shell
- project can be created and persisted

### Exit Criteria
- `POST /projects` works
- project list UI works
- local project directory is created successfully

---

## Sprint 1 — Ingestion
### Goals
- import source files and normalize manuscript text

### Tasks
- implement TXT parser
- implement Markdown parser
- implement DOCX parser
- implement EPUB parser
- define canonical manuscript JSON structure
- store source manifest
- create source import API
- build source import UI
- show parser warnings

### Deliverables
- manuscript import pipeline
- canonical manuscript persisted
- source manifest generated

### Exit Criteria
- at least TXT + DOCX + EPUB import works on sample fixtures

---

## Sprint 2 — Structure Extraction
### Goals
- convert manuscript into chapters, scenes, and segments

### Tasks
- chapter boundary detection
- scene segmentation heuristics
- dialogue block detection
- segment generation rules
- create structure manifest
- populate chapters/scenes/segments tables
- chapter/scene/segment viewer UI
- allow manual segment text edits

### Deliverables
- structured project viewer
- editable segments

### Exit Criteria
- a manuscript becomes a browsable structured project

---

## Sprint 3 — Character Registry & Casting
### Goals
- create character map and voice assignment flow

### Tasks
- character candidate extraction
- character CRUD APIs
- voice profile CRUD APIs
- character-to-voice assignment API
- narrator default voice support
- pronunciation dictionary CRUD
- character/casting UI

### Deliverables
- cast builder screen
- voice bible scaffold

### Exit Criteria
- narrator + at least several characters can be mapped to voices

---

## Sprint 4 — Voice Preview and Direction
### Goals
- preview voices and encode delivery rules

### Tasks
- define TTS adapter interface
- implement mock adapter for dev
- implement first real local adapter
- voice preview endpoint
- scene direction schema
- direction defaults UI
- per-segment direction override editing
- direction manifest generation

### Deliverables
- voice preview workflow
- segment direction configuration

### Exit Criteria
- user can preview selected voice with style prompt and save direction settings

---

## Sprint 5 — Segment Generation
### Goals
- generate audio at segment level

### Tasks
- segment render request contract
- render cache key generation
- segment render storage
- segment_renders table usage
- waveform metadata generation
- single-segment generation endpoint
- segment generation controls in UI

### Deliverables
- per-segment generation works
- render history stored

### Exit Criteria
- one segment can be rendered, replayed, and regenerated

---

## Sprint 6 — Chapter Assembly
### Goals
- combine segment renders into chapter output

### Tasks
- ordered segment retrieval
- pause insertion logic
- speech stem assembly
- chapter render records
- chapter assembly manifest
- chapter playback UI
- chapter generation API

### Deliverables
- full chapter speech render
- chapter timeline playback

### Exit Criteria
- one chapter can be generated from segment renders end-to-end

---

## Sprint 7 — Review and Patch Loop
### Goals
- make bad lines easy to fix

### Tasks
- issue model and issue API
- automated QA checks: missing audio, clipping, silence, truncation
- comments model and API
- mark-reviewed flow
- regenerate specific segment from chapter screen
- stale chapter render invalidation
- chapter reassembly after patch

### Deliverables
- review queue
- issue list
- selective patch workflow

### Exit Criteria
- user can detect a bad line, regenerate it, and reassemble chapter

---

## Sprint 8 — Ambience and Light Cinematic Layer
### Goals
- add subtle production value without harming clarity

### Tasks
- ambience profile model
- ambience asset referencing/import
- ambience stem assembly
- ambience intensity controls
- speech vs ambience gain controls
- chapter render mode: `speech_only`, `multi_voice`, `light_cinematic`

### Deliverables
- optional ambience layer
- chapter mix preview

### Exit Criteria
- user can export with or without ambience

---

## Sprint 9 — Export and Packaging
### Goals
- produce shareable audio outputs

### Tasks
- export job flow
- WAV export
- MP3 export
- M4B package export
- metadata form UI
- export manifest generation
- output validation

### Deliverables
- export workflow
- packaged audiobook outputs

### Exit Criteria
- a chaptered draft can be exported successfully

---

## Sprint 10 — Alpha Hardening
### Goals
- stabilize the MVP for external testers

### Tasks
- add retry/resume behavior for jobs
- improve parser error handling
- improve debug logs and debug bundle export
- profile slow steps
- fix UI rough edges
- run sample-book test matrix
- conduct 5–10 alpha user trials

### Deliverables
- private alpha build
- known issues list
- prioritized stabilization backlog

### Exit Criteria
- external users can complete core workflow without engineering assistance

---

## 8.4 Prioritization Rules
If time is constrained, cut in this order:
1. advanced ambience features
2. rich comments UX
3. complex scene mood inference
4. aggressive automated QA sophistication
5. M4B packaging polish

Never cut:
- import and structure
- voice assignment
- segment generation
- chapter assembly
- selective regeneration
- export

## 8.5 Engineering Risks
### Risk 1 — Parsing quality is inconsistent across manuscripts
Mitigation: start with well-formed EPUB/DOCX/TXT and strong manual correction UX.

### Risk 2 — Local TTS latency is too slow
Mitigation: segment caching, preview mode, chapter batching, resumable jobs.

### Risk 3 — Character attribution is noisy
Mitigation: surface low-confidence results and make manual correction fast.

### Risk 4 — Audio quality feels gimmicky
Mitigation: default to restrained production and prioritize clarity.

### Risk 5 — Project state becomes hard to recover after failures
Mitigation: manifest-driven outputs, append-only render history, explicit job states.

## 8.6 MVP Release Checklist
- project creation works
- import works for core formats
- chapters/scenes/segments visible
- character and voice mapping works
- voice preview works
- single segment generation works
- full chapter generation works
- segment regeneration works
- issue list works
- export works
- rights declaration gating works
- project reload works

## 8.7 Recommended First Backlog After MVP
- hosted async workers
- shared voice libraries
- improved speaker attribution
- stronger pronunciation tooling
- better waveform/timeline editor
- collaboration and approvals
- publisher rights workflows

## 8.8 Final MVP Definition of Done
The MVP is done when a real user can, without engineering intervention:
1. create a project,
2. import a manuscript,
3. review structure,
4. assign voices,
5. generate a chapter,
6. patch weak segments,
7. export an audiobook draft they would actually share.

