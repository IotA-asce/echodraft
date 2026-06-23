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


class SceneRecord(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


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


class CharacterRecord(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    role_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class VoiceProfileRecord(Base):
    __tablename__ = "voice_profiles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    backend: Mapped[str] = mapped_column(String(100), nullable=False)
    style_prompt: Mapped[str | None] = mapped_column(Text)


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
