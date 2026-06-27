from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobRecord(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelInstallationRecord(Base):
    __tablename__ = "model_installations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str | None] = mapped_column(String(200))
    install_path: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    size_bytes: Mapped[int | None] = mapped_column()
    license_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ModelInstallJobRecord(Base):
    __tablename__ = "model_install_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percent: Mapped[int] = mapped_column(nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(200))
    logs_path: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class LlmRunRecord(Base):
    __tablename__ = "llm_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_path: Mapped[str | None] = mapped_column(Text)
    response_path: Mapped[str | None] = mapped_column(Text)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RightsDeclarationRecord(Base):
    __tablename__ = "rights_declarations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    declaration_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_path: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceDocumentRecord(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rights_status: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_path: Mapped[str | None] = mapped_column(Text)
    manifest_path: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class SourcePageRecord(Base):
    __tablename__ = "source_pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text)
    embedded_text_path: Mapped[str | None] = mapped_column(Text)
    selected_text_path: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class OcrRunRecord(Base):
    __tablename__ = "ocr_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class OcrPageResultRecord(Base):
    __tablename__ = "ocr_page_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ocr_run_id: Mapped[str] = mapped_column(ForeignKey("ocr_runs.id"), nullable=False, index=True)
    source_page_id: Mapped[str] = mapped_column(
        ForeignKey("source_pages.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    text_path: Mapped[str] = mapped_column(Text, nullable=False)
    json_path: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class CanonicalSpanRecord(Base):
    __tablename__ = "canonical_spans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(nullable=False)
    canonical_start_offset: Mapped[int] = mapped_column(nullable=False)
    canonical_end_offset: Mapped[int] = mapped_column(nullable=False)
    source_text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    bbox_json: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)


class CleaningRunRecord(Base):
    __tablename__ = "cleaning_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_path: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class TextCleanlinessIssueRecord(Base):
    __tablename__ = "text_cleanliness_issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id"), nullable=False, index=True
    )
    canonical_span_start: Mapped[int] = mapped_column(nullable=False)
    canonical_span_end: Mapped[int] = mapped_column(nullable=False)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_fix: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    resolved_by_user: Mapped[bool] = mapped_column(nullable=False, default=False)


class ChapterRecord(Base):
    __tablename__ = "chapters"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)


class SceneRecord(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)


class SegmentRecord(Base):
    __tablename__ = "segments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    segment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    speaker_candidate: Mapped[str | None] = mapped_column(String(128))
    speaker_confidence: Mapped[float] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)


class StructureParserWarningRecord(Base):
    __tablename__ = "structure_parser_warnings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("source_documents.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    confidence: Mapped[float] = mapped_column(nullable=False)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StructureLockRecord(Base):
    __tablename__ = "structure_locks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentRevisionRecord(Base):
    __tablename__ = "segment_revisions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SegmentRenderRecord(Base):
    __tablename__ = "segment_renders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), index=True)
    render_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    audio_path: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(nullable=False)
    parent_render_id: Mapped[str | None] = mapped_column(String(64))
    request_json: Mapped[str] = mapped_column(Text, nullable=False)


class ChapterRenderRecord(Base):
    __tablename__ = "chapter_renders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    speech_path: Mapped[str] = mapped_column(Text)
    manifest_path: Mapped[str] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column()
    render_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="speech_only")
    ambience_stem_path: Mapped[str | None] = mapped_column(Text)
    mixed_audio_path: Mapped[str | None] = mapped_column(Text)


class AmbienceAssetRecord(Base):
    __tablename__ = "ambience_assets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_path: Mapped[str] = mapped_column(Text, nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(Text, nullable=False)


class AmbienceProfileRecord(Base):
    __tablename__ = "ambience_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    gain_db: Mapped[float] = mapped_column(nullable=False)


class AmbienceCueRecord(Base):
    __tablename__ = "ambience_cues"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("ambience_assets.id"))
    gain_db: Mapped[float] = mapped_column(nullable=False)
    fade_in_ms: Mapped[int] = mapped_column(nullable=False)
    fade_out_ms: Mapped[int] = mapped_column(nullable=False)
    no_sfx: Mapped[bool] = mapped_column(nullable=False, default=False)


class IssueRecord(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id"), index=True)
    segment_id: Mapped[str | None] = mapped_column(ForeignKey("segments.id"), index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    dedupe_key: Mapped[str | None] = mapped_column(String(256), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommentRecord(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id"), index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PatchAttemptRecord(Base):
    __tablename__ = "patch_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("issues.id"), index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), index=True)
    old_render_id: Mapped[str | None] = mapped_column(ForeignKey("segment_renders.id"))
    new_render_id: Mapped[str] = mapped_column(ForeignKey("segment_renders.id"), nullable=False)
    chapter_render_id: Mapped[str] = mapped_column(ForeignKey("chapter_renders.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExportPackageRecord(Base):
    __tablename__ = "export_packages"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_path: Mapped[str] = mapped_column(Text, nullable=False)
    archive_path: Mapped[str | None] = mapped_column(Text)


class CharacterRecord(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(200))
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    traits_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    first_seen_source_id: Mapped[str | None] = mapped_column(String(64))
    first_seen_chapter_id: Mapped[str | None] = mapped_column(String(64))
    first_seen_segment_id: Mapped[str | None] = mapped_column(String(64))
    merge_history_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    split_history_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    merged_into_character_id: Mapped[str | None] = mapped_column(String(64))
    role_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class VoiceProfileRecord(Base):
    __tablename__ = "voice_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    backend: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_voice_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    style_prompt: Mapped[str | None] = mapped_column(Text)


class ProjectProductionSettingsRecord(Base):
    __tablename__ = "project_production_settings"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    narrator_voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"))
    default_direction_json: Mapped[str | None] = mapped_column(Text)


class SegmentProductionOverrideRecord(Base):
    __tablename__ = "segment_production_overrides"
    segment_id: Mapped[str] = mapped_column(ForeignKey("segments.id"), primary_key=True)
    voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"))
    direction_json: Mapped[str | None] = mapped_column(Text)


class CharacterVoiceAssignmentRecord(Base):
    __tablename__ = "character_voice_assignments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), unique=True)
    voice_profile_id: Mapped[str] = mapped_column(ForeignKey("voice_profiles.id"))


class PronunciationEntryRecord(Base):
    __tablename__ = "pronunciation_entries"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    phonetic: Mapped[str | None] = mapped_column(String(200))
    replacement_text: Mapped[str | None] = mapped_column(String(200))
