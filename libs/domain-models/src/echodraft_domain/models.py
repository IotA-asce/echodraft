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
    provider_voice_id: str = Field(alias="providerVoiceId")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class VoiceProfileCreate(ApiModel):
    name: str
    backend: str
    provider_voice_id: str = Field(min_length=1, alias="providerVoiceId")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class VoiceProfileUpdate(ApiModel):
    name: str | None = None
    provider_voice_id: str | None = Field(default=None, alias="providerVoiceId")
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


class DirectionProfile(ApiModel):
    scope_type: str = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    pace: float = Field(default=1.0, ge=0.5, le=2.0)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    tone: str = "neutral"
    style_prompt: str | None = Field(default=None, alias="stylePrompt")
    emphasis: bool = False
    whisper: bool = False
    no_sfx: bool = Field(default=True, alias="noSfx")


class VoicePreviewRequest(ApiModel):
    text: str = Field(min_length=1, max_length=1000)
    voice_profile_id: str = Field(alias="voiceProfileId")
    direction: DirectionProfile


class VoicePreview(ApiModel):
    asset_path: str = Field(alias="assetPath")
    adapter: str
    model_version: str = Field(alias="modelVersion")
    direction: DirectionProfile
    audio_url: str | None = Field(default=None, alias="audioUrl")


class TtsSettings(ApiModel):
    provider: str = "mock"
    setup_mode: str | None = Field(default=None, alias="setupMode")
    executable: str | None = None
    runtime_root: str | None = Field(default=None, alias="runtimeRoot")
    python_path: str | None = Field(default=None, alias="pythonPath")
    model_path: str | None = Field(default=None, alias="modelPath")
    voices_data_path: str | None = Field(default=None, alias="voicesDataPath")
    voice_registry_path: str | None = Field(default=None, alias="voiceRegistryPath")
    ready: bool = False
    message: str | None = None
    available_voices: list[str] = Field(default_factory=list, alias="availableVoices")


class TtsSettingsUpdate(ApiModel):
    provider: str
    setup_mode: str | None = Field(default=None, alias="setupMode")
    executable: str | None = None
    runtime_root: str | None = Field(default=None, alias="runtimeRoot")
    python_path: str | None = Field(default=None, alias="pythonPath")
    model_path: str | None = Field(default=None, alias="modelPath")
    voices_data_path: str | None = Field(default=None, alias="voicesDataPath")
    voice_registry_path: str | None = Field(default=None, alias="voiceRegistryPath")


class TtsTestRequest(ApiModel):
    text: str = Field(default="Echodraft is ready to produce your audiobook.", min_length=1, max_length=1000)
    voice_id: str | None = Field(default=None, alias="voiceId")


class KokoroSetupStep(ApiModel):
    phase: str
    label: str
    status: str
    message: str | None = None


class KokoroSetupStatus(ApiModel):
    platform: str
    state: str
    setup_mode: str = Field(alias="setupMode")
    runtime_root: str = Field(alias="runtimeRoot")
    python_path: str = Field(alias="pythonPath")
    executable: str
    model_path: str = Field(alias="modelPath")
    voices_data_path: str = Field(alias="voicesDataPath")
    voice_registry_path: str = Field(alias="voiceRegistryPath")
    ready: bool
    message: str | None = None
    next_action: str = Field(alias="nextAction")
    available_voices: list[str] = Field(default_factory=list, alias="availableVoices")
    steps: list[KokoroSetupStep] = Field(default_factory=list)


class KokoroSetupInstallRequest(ApiModel):
    confirm_network_download: bool = Field(alias="confirmNetworkDownload")
    confirm_third_party_license: bool = Field(alias="confirmThirdPartyLicense")
    repair: bool = False


class ProjectProductionSettings(ApiModel):
    project_id: str = Field(alias="projectId")
    narrator_voice_profile_id: str | None = Field(default=None, alias="narratorVoiceProfileId")
    default_direction: DirectionProfile | None = Field(default=None, alias="defaultDirection")


class ProjectProductionSettingsUpdate(ApiModel):
    narrator_voice_profile_id: str | None = Field(default=None, alias="narratorVoiceProfileId")
    default_direction: DirectionProfile | None = Field(default=None, alias="defaultDirection")


class SegmentProductionOverride(ApiModel):
    segment_id: str = Field(alias="segmentId")
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")
    direction: DirectionProfile | None = None


class SegmentProductionOverrideUpdate(ApiModel):
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")
    direction: DirectionProfile | None = None


class SegmentRenderRequest(ApiModel):
    voice_profile_id: str = Field(alias="voiceProfileId")
    direction: DirectionProfile
    output_format: str = Field(default="wav", alias="outputFormat")
    force: bool = False


class SegmentRender(ApiModel):
    id: str
    segment_id: str = Field(alias="segmentId")
    render_key: str = Field(alias="renderKey")
    status: str
    audio_path: str = Field(alias="audioPath")
    metadata_path: str = Field(alias="metadataPath")
    duration_ms: int = Field(alias="durationMs")
    parent_render_id: str | None = Field(default=None, alias="parentRenderId")
    audio_url: str | None = Field(default=None, alias="audioUrl")


class ChapterRender(ApiModel):
    id: str
    chapter_id: str = Field(alias="chapterId")
    status: str
    speech_path: str = Field(alias="speechPath")
    manifest_path: str = Field(alias="manifestPath")
    duration_ms: int = Field(alias="durationMs")
    render_mode: str = Field(default="speech_only", alias="renderMode")
    ambience_stem_path: str | None = Field(default=None, alias="ambienceStemPath")
    mixed_audio_path: str | None = Field(default=None, alias="mixedAudioPath")
    audio_url: str | None = Field(default=None, alias="audioUrl")


class ChapterAssemblyRequest(ApiModel):
    render_mode: str = Field(default="speech_only", alias="renderMode")


class AmbienceAsset(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    asset_path: str = Field(alias="assetPath")
    license_note: str = Field(alias="licenseNote")
    provenance: str


class AmbienceAssetCreate(ApiModel):
    name: str
    asset_path: str = Field(alias="assetPath")
    license_note: str = Field(alias="licenseNote")
    provenance: str


class AmbienceProfile(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    gain_db: float = Field(alias="gainDb")


class AmbienceProfileCreate(ApiModel):
    name: str
    gain_db: float = Field(default=-24.0, alias="gainDb")


class AmbienceCue(ApiModel):
    id: str
    scene_id: str = Field(alias="sceneId")
    asset_id: str | None = Field(default=None, alias="assetId")
    gain_db: float = Field(alias="gainDb")
    fade_in_ms: int = Field(alias="fadeInMs")
    fade_out_ms: int = Field(alias="fadeOutMs")
    no_sfx: bool = Field(alias="noSfx")


class AmbienceCueCreate(ApiModel):
    scene_id: str = Field(alias="sceneId")
    asset_id: str | None = Field(default=None, alias="assetId")
    gain_db: float = Field(default=-24.0, alias="gainDb")
    fade_in_ms: int = Field(default=500, alias="fadeInMs")
    fade_out_ms: int = Field(default=500, alias="fadeOutMs")
    no_sfx: bool = Field(default=False, alias="noSfx")


class Issue(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    segment_id: str | None = Field(default=None, alias="segmentId")
    severity: str
    category: str
    title: str
    description: str
    status: str
    metadata: dict[str, object] = Field(default_factory=dict)


class IssueCreate(ApiModel):
    chapter_id: str | None = Field(default=None, alias="chapterId")
    segment_id: str | None = Field(default=None, alias="segmentId")
    severity: str = "warning"
    category: str
    title: str
    description: str


class IssueUpdate(ApiModel):
    status: str | None = None
    severity: str | None = None


class Comment(ApiModel):
    id: str
    issue_id: str = Field(alias="issueId")
    body: str
    author: str
    created_at: datetime = Field(alias="createdAt")


class CommentCreate(ApiModel):
    body: str = Field(min_length=1)
    author: str = "local-user"


class SegmentPatchRequest(SegmentRenderRequest):
    text_content: str | None = Field(default=None, alias="textContent")
    issue_id: str | None = Field(default=None, alias="issueId")


class SegmentPatchResult(ApiModel):
    segment: Segment
    render: SegmentRender
    chapter_render: ChapterRender = Field(alias="chapterRender")


class ExportPackage(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    format: str
    status: str
    output_path: str = Field(alias="outputPath")
    manifest_path: str = Field(alias="manifestPath")
    archive_path: str | None = Field(default=None, alias="archivePath")
    download_url: str | None = Field(default=None, alias="downloadUrl")


class ExportRequest(ApiModel):
    format: str = "wav"
    chapter_ids: list[str] = Field(default_factory=list, alias="chapterIds")


class ChapterProductionStatus(ApiModel):
    chapter_id: str = Field(alias="chapterId")
    ready: bool
    reason: str | None = None
    total_segments: int = Field(alias="totalSegments")
    current_segments: int = Field(alias="currentSegments")
    active_render: ChapterRender | None = Field(default=None, alias="activeRender")
