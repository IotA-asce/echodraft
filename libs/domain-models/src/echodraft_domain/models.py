from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class RightsStatus(StrEnum):
    DECLARED = "declared"
    NOT_DECLARED = "not_declared"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ProjectCreate(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    rights_status: RightsStatus = Field(alias="rightsStatus")

    @model_validator(mode="after")
    def require_rights_declaration(self) -> Self:
        if self.rights_status is not RightsStatus.DECLARED:
            raise ValueError("A declared rights status is required to create a project.")
        return self


class Project(ApiModel):
    id: str
    title: str
    author: str | None = None
    description: str | None = None
    rights_status: RightsStatus = Field(alias="rightsStatus")
    status: str
    artifact_path: str = Field(alias="artifactPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class Job(ApiModel):
    id: str
    project_id: str | None = Field(default=None, alias="projectId")
    job_type: str = Field(alias="jobType")
    target_id: str | None = Field(default=None, alias="targetId")
    status: JobState
    progress: dict[str, object] = Field(default_factory=dict)
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


class RightsDeclaration(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    declaration_type: str = Field(alias="declarationType")
    status: RightsStatus
    created_at: datetime = Field(alias="createdAt")


class ParserWarning(ApiModel):
    severity: WarningSeverity
    source_range: str | None = Field(default=None, alias="sourceRange")
    message: str
    suggested_action: str | None = Field(default=None, alias="suggestedAction")


class SourceDocument(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    original_filename: str = Field(alias="originalFilename")
    mime_type: str = Field(alias="mimeType")
    checksum: str
    imported_at: datetime = Field(alias="importedAt")
    rights_status: RightsStatus = Field(alias="rightsStatus")
    parser_version: str = Field(alias="parserVersion")
    original_path: str = Field(alias="originalPath")
    canonical_path: str | None = Field(default=None, alias="canonicalPath")
    manifest_path: str | None = Field(default=None, alias="manifestPath")
    status: str
    warnings: list[ParserWarning] = Field(default_factory=list)
    preview: str | None = None


class StructureRequest(ApiModel):
    max_segment_chars: int = Field(default=600, ge=120, le=2000, alias="maxSegmentChars")


class SegmentUpdate(ApiModel):
    text_content: str = Field(min_length=1, alias="textContent")


class ReparseRequest(ApiModel):
    parser_version: str = Field(default="ingestion-0.1.0", alias="parserVersion")


class Chapter(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    order_index: int = Field(alias="orderIndex")
    status: str
    title: str | None = None
    confidence: float
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")


class Scene(ApiModel):
    id: str
    chapter_id: str = Field(alias="chapterId")
    order_index: int = Field(alias="orderIndex")
    status: str
    confidence: float
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")


class Segment(ApiModel):
    id: str
    scene_id: str = Field(alias="sceneId")
    order_index: int = Field(alias="orderIndex")
    text_content: str = Field(alias="textContent")
    status: str
    normalized_text: str = Field(alias="normalizedText")
    segment_type: str = Field(alias="segmentType")
    speaker_candidate: str | None = Field(default=None, alias="speakerCandidate")
    speaker_confidence: float = Field(alias="speakerConfidence")
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")
    revision: int


class SegmentRevision(ApiModel):
    id: str
    segment_id: str = Field(alias="segmentId")
    revision: int
    text_content: str = Field(alias="textContent")
    created_at: datetime = Field(alias="createdAt")


class Character(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    display_name: str = Field(alias="displayName")
    aliases: list[str] = []
    role_type: str = Field(alias="roleType")
    confidence: float
    notes: str | None = None


class CharacterCreate(ApiModel):
    display_name: str = Field(min_length=1, alias="displayName")
    aliases: list[str] = []
    role_type: str = Field(default="major", alias="roleType")
    confidence: float = 1.0
    notes: str | None = None


class VoiceProfile(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    backend: str
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class VoiceProfileCreate(ApiModel):
    name: str
    backend: str
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class AssignVoice(ApiModel):
    voice_profile_id: str = Field(alias="voiceProfileId")


class PronunciationEntry(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    term: str
    phonetic: str | None = None
    replacement_text: str | None = Field(default=None, alias="replacementText")


class PronunciationCreate(ApiModel):
    term: str
    phonetic: str | None = None
    replacement_text: str | None = Field(default=None, alias="replacementText")


class Issue(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    severity: str
    category: str
    title: str


class ExportPackage(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    format: str
    status: str
