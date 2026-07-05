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
    structure_signals_path: str | None = Field(default=None, alias="structureSignalsPath")
    status: str
    warnings: list[ParserWarning] = Field(default_factory=list)
    preview: str | None = None


class SourcePage(ApiModel):
    id: str
    source_document_id: str = Field(alias="sourceDocumentId")
    page_number: int = Field(alias="pageNumber")
    image_path: str | None = Field(default=None, alias="imagePath")
    image_url: str | None = Field(default=None, alias="imageUrl")
    embedded_text_path: str | None = Field(default=None, alias="embeddedTextPath")
    selected_text_path: str | None = Field(default=None, alias="selectedTextPath")
    extraction_method: str = Field(alias="extractionMethod")
    confidence: float
    warnings: list[ParserWarning] = Field(default_factory=list)
    preview: str | None = None


class OcrRun(ApiModel):
    id: str
    source_document_id: str = Field(alias="sourceDocumentId")
    provider: str
    status: str
    settings: dict[str, object] = Field(default_factory=dict)
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")


class OcrPageResult(ApiModel):
    id: str
    ocr_run_id: str = Field(alias="ocrRunId")
    source_page_id: str = Field(alias="sourcePageId")
    page_number: int = Field(alias="pageNumber")
    text_path: str = Field(alias="textPath")
    json_path: str = Field(alias="jsonPath")
    confidence: float
    warnings: list[ParserWarning] = Field(default_factory=list)


class CanonicalSpan(ApiModel):
    id: str
    source_document_id: str = Field(alias="sourceDocumentId")
    page_number: int = Field(alias="pageNumber")
    canonical_start_offset: int = Field(alias="canonicalStartOffset")
    canonical_end_offset: int = Field(alias="canonicalEndOffset")
    source_text_hash: str = Field(alias="sourceTextHash")
    bbox: list[float] | None = None
    extraction_method: str = Field(alias="extractionMethod")
    confidence: float


class CleaningRun(ApiModel):
    id: str
    source_document_id: str = Field(alias="sourceDocumentId")
    status: str
    manifest_path: str | None = Field(default=None, alias="manifestPath")
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")


class TextCleanlinessIssue(ApiModel):
    id: str
    source_document_id: str = Field(alias="sourceDocumentId")
    canonical_span_start: int = Field(alias="canonicalSpanStart")
    canonical_span_end: int = Field(alias="canonicalSpanEnd")
    issue_type: str = Field(alias="issueType")
    severity: str
    suggested_fix: str | None = Field(default=None, alias="suggestedFix")
    confidence: float
    status: str
    resolved_by_user: bool = Field(default=False, alias="resolvedByUser")


class TextCleanlinessIssueUpdate(ApiModel):
    status: str | None = None
    resolved_by_user: bool | None = Field(default=None, alias="resolvedByUser")


class StructureRequest(ApiModel):
    max_segment_chars: int = Field(default=600, ge=120, le=2000, alias="maxSegmentChars")


class SegmentUpdate(ApiModel):
    text_content: str = Field(min_length=1, alias="textContent")


class ChapterUpdate(ApiModel):
    title: str | None = Field(default=None, max_length=512)
    status: str | None = None


class SceneUpdate(ApiModel):
    status: str | None = None


class StructureLockUpdate(ApiModel):
    locked: bool = True
    reason: str | None = Field(default=None, max_length=500)


class SegmentSplitRequest(ApiModel):
    split_offset: int = Field(alias="splitOffset", gt=0)


class SegmentMergeRequest(ApiModel):
    next_segment_id: str = Field(alias="nextSegmentId")


class StructureParserWarning(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    source_document_id: str | None = Field(default=None, alias="sourceDocumentId")
    scope_type: str = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    severity: str
    message: str
    evidence: dict[str, object] = Field(default_factory=dict)
    confidence: float
    resolved: bool = False
    created_at: datetime = Field(alias="createdAt")


class StructureQuality(ApiModel):
    chapter_count: int = Field(alias="chapterCount")
    chapters_from_container_signals: int = Field(default=0, alias="chaptersFromContainerSignals")
    scene_count: int = Field(alias="sceneCount")
    segment_count: int = Field(alias="segmentCount")
    dialogue_segment_count: int = Field(alias="dialogueSegmentCount")
    dialogue_attribution_coverage: float = Field(alias="dialogueAttributionCoverage")
    unresolved_dialogue_count: int = Field(alias="unresolvedDialogueCount")
    average_segment_chars: float = Field(alias="averageSegmentChars")
    long_segment_count: int = Field(alias="longSegmentCount")
    mixed_segment_warning_count: int = Field(alias="mixedSegmentWarningCount")
    cast_candidate_count: int = Field(alias="castCandidateCount")
    possible_duplicate_cast_count: int = Field(alias="possibleDuplicateCastCount")
    low_confidence_cast_candidate_count: int = Field(alias="lowConfidenceCastCandidateCount")
    possible_scene_break_count: int = Field(alias="possibleSceneBreakCount")
    offset_validation_failure_count: int = Field(alias="offsetValidationFailureCount")
    quote_unclosed_count: int = Field(alias="quoteUnclosedCount")
    warnings_needing_review_count: int = Field(alias="warningsNeedingReviewCount")
    llm_refinement_used: bool = Field(alias="llmRefinementUsed")
    llm_accepted_batch_count: int = Field(alias="llmAcceptedBatchCount")
    llm_rejected_batch_count: int = Field(alias="llmRejectedBatchCount")


class LlmRun(ApiModel):
    id: str
    project_id: str | None = Field(default=None, alias="projectId")
    source_document_id: str | None = Field(default=None, alias="sourceDocumentId")
    provider: str
    model: str
    task: str
    status: str
    prompt_path: str | None = Field(default=None, alias="promptPath")
    response_path: str | None = Field(default=None, alias="responsePath")
    output_schema: dict[str, object] = Field(default_factory=dict, alias="schema")
    result: dict[str, object] | None = None
    error_message: str | None = Field(default=None, alias="errorMessage")
    retries: int = 0
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")


class LlmExtractionRequest(ApiModel):
    model: str = "qwen3:4b"
    task: str = "structure_candidates"
    source_document_id: str | None = Field(default=None, alias="sourceDocumentId")
    output_schema: dict[str, object] | None = Field(default=None, alias="schema")
    prompt: str | None = None


class LlmExtractionResult(ApiModel):
    run: LlmRun
    result: dict[str, object]


class EmbeddingRequest(ApiModel):
    model: str = "qwen3-embedding"
    input: str | list[str]


class EmbeddingResult(ApiModel):
    model: str
    embeddings: list[list[float]]


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
    parser_evidence: dict[str, object] = Field(default_factory=dict, alias="parserEvidence")
    user_locked: bool = Field(default=False, alias="userLocked")
    lock_reason: str | None = Field(default=None, alias="lockReason")


class Scene(ApiModel):
    id: str
    chapter_id: str = Field(alias="chapterId")
    order_index: int = Field(alias="orderIndex")
    status: str
    confidence: float
    start_offset: int = Field(alias="startOffset")
    end_offset: int = Field(alias="endOffset")
    parser_evidence: dict[str, object] = Field(default_factory=dict, alias="parserEvidence")
    user_locked: bool = Field(default=False, alias="userLocked")
    lock_reason: str | None = Field(default=None, alias="lockReason")


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
    parser_evidence: dict[str, object] = Field(default_factory=dict, alias="parserEvidence")
    user_locked: bool = Field(default=False, alias="userLocked")
    lock_reason: str | None = Field(default=None, alias="lockReason")
    revision: int


class SpeakerAttribution(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    segment_id: str = Field(alias="segmentId")
    character_id: str | None = Field(default=None, alias="characterId")
    speaker_name: str | None = Field(default=None, alias="speakerName")
    method: str
    evidence: dict[str, object] = Field(default_factory=dict)
    confidence: float
    status: str
    user_locked: bool = Field(default=False, alias="userLocked")
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class SpeakerAttributionUpdate(ApiModel):
    character_id: str | None = Field(default=None, alias="characterId")
    speaker_name: str | None = Field(default=None, alias="speakerName")
    status: str | None = None
    user_locked: bool | None = Field(default=None, alias="userLocked")


class SpeakerAttributionUpdateResult(SpeakerAttribution):
    """Attribution PATCH response.

    Adds ``propagatedCount`` (how many sibling rows a confirmation taught) on top
    of every existing SpeakerAttribution field, so older clients keep working.
    """

    propagated_count: int = Field(default=0, alias="propagatedCount")


class SpeakerAttributionRunRequest(ApiModel):
    use_local_llm: bool = Field(default=False, alias="useLocalLlm")
    model: str = "qwen3:4b"


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
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    aliases: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    first_seen_source_id: str | None = Field(default=None, alias="firstSeenSourceId")
    first_seen_chapter_id: str | None = Field(default=None, alias="firstSeenChapterId")
    first_seen_segment_id: str | None = Field(default=None, alias="firstSeenSegmentId")
    role_type: str = Field(alias="roleType")
    confidence: float
    notes: str | None = None
    merge_history: list[dict[str, object]] = Field(default_factory=list, alias="mergeHistory")
    split_history: list[dict[str, object]] = Field(default_factory=list, alias="splitHistory")
    user_locked: bool = Field(default=False, alias="userLocked")
    lock_reason: str | None = Field(default=None, alias="lockReason")
    merged_into_character_id: str | None = Field(default=None, alias="mergedIntoCharacterId")
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")


class CharacterCreate(ApiModel):
    display_name: str = Field(min_length=1, alias="displayName")
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    aliases: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    first_seen_source_id: str | None = Field(default=None, alias="firstSeenSourceId")
    first_seen_chapter_id: str | None = Field(default=None, alias="firstSeenChapterId")
    first_seen_segment_id: str | None = Field(default=None, alias="firstSeenSegmentId")
    role_type: str = Field(default="major", alias="roleType")
    confidence: float = 1.0
    notes: str | None = None


class CharacterUpdate(ApiModel):
    display_name: str | None = Field(default=None, alias="displayName", min_length=1)
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    aliases: list[str] | None = None
    traits: list[str] | None = None
    role_type: str | None = Field(default=None, alias="roleType")
    confidence: float | None = None
    notes: str | None = None
    user_locked: bool | None = Field(default=None, alias="userLocked")
    lock_reason: str | None = Field(default=None, alias="lockReason")
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")


class CharacterMergeRequest(ApiModel):
    source_character_id: str = Field(alias="sourceCharacterId")
    reason: str | None = None


class CharacterSplitRequest(ApiModel):
    display_name: str = Field(min_length=1, alias="displayName")
    aliases: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    reason: str | None = None


class CharacterRejectMergeRequest(ApiModel):
    candidate_name: str = Field(alias="candidateName", min_length=1)
    reason: str | None = None


class VoiceProfile(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    backend: str
    provider_voice_id: str = Field(alias="providerVoiceId")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")
    facets: list[str] = Field(default_factory=list)


class VoiceProfileCreate(ApiModel):
    name: str
    backend: str
    provider_voice_id: str = Field(min_length=1, alias="providerVoiceId")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class VoiceProfileUpdate(ApiModel):
    name: str | None = None
    provider_voice_id: str | None = Field(default=None, alias="providerVoiceId")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")


class VoiceSuggestion(ApiModel):
    voice_profile_id: str = Field(alias="voiceProfileId")
    name: str
    provider_voice_id: str = Field(alias="providerVoiceId")
    backend: str
    score: float
    matched_traits: list[str] = Field(default_factory=list, alias="matchedTraits")
    facets: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    sample_text: str = Field(alias="sampleText")


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
    emotion: str = "neutral"
    pause_before_ms: int = Field(default=0, ge=0, le=5000, alias="pauseBeforeMs")
    pause_after_ms: int = Field(default=0, ge=0, le=5000, alias="pauseAfterMs")
    style_prompt: str | None = Field(default=None, alias="stylePrompt")
    emphasis: bool = False
    whisper: bool = False
    no_sfx: bool = Field(default=True, alias="noSfx")


class SegmentDirection(ApiModel):
    segment_id: str = Field(alias="segmentId")
    project_id: str = Field(alias="projectId")
    direction: DirectionProfile
    source: str
    user_locked: bool = Field(default=False, alias="userLocked")
    evidence: dict[str, object] = Field(default_factory=dict)
    direction_fingerprint: str = Field(alias="directionFingerprint")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class DirectionInferenceRunRequest(ApiModel):
    use_local_llm: bool = Field(default=False, alias="useLocalLlm")
    model: str = "qwen3:4b"


class SegmentDirectionUpdate(ApiModel):
    direction: DirectionProfile
    user_locked: bool = Field(default=True, alias="userLocked")


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
    piper_model_path: str | None = Field(default=None, alias="piperModelPath")
    piper_config_path: str | None = Field(default=None, alias="piperConfigPath")
    reference_voice_path: str | None = Field(default=None, alias="referenceVoicePath")
    reference_voice_consent: bool = Field(default=False, alias="referenceVoiceConsent")
    language: str = "en"
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
    piper_model_path: str | None = Field(default=None, alias="piperModelPath")
    piper_config_path: str | None = Field(default=None, alias="piperConfigPath")
    reference_voice_path: str | None = Field(default=None, alias="referenceVoicePath")
    reference_voice_consent: bool = Field(default=False, alias="referenceVoiceConsent")
    language: str = "en"


class TtsProviderInfo(ApiModel):
    provider: str
    display_name: str = Field(alias="displayName")
    setup_mode: str | None = Field(default=None, alias="setupMode")
    ready: bool
    message: str | None = None
    available_voices: list[str] = Field(default_factory=list, alias="availableVoices")
    capabilities: dict[str, object] = Field(default_factory=dict)
    requires_reference_consent: bool = Field(default=False, alias="requiresReferenceConsent")
    reference_voice_consent: bool | None = Field(default=None, alias="referenceVoiceConsent")
    reference_voice_path: str | None = Field(default=None, alias="referenceVoicePath")


class TtsWorkerStatus(ApiModel):
    provider: str
    setup_mode: str | None = Field(default=None, alias="setupMode")
    worker_mode: str = Field(alias="workerMode")
    state: str
    pid: int | None = None
    request_count: int = Field(default=0, alias="requestCount")
    last_error: str | None = Field(default=None, alias="lastError")


class TtsTestRequest(ApiModel):
    text: str = Field(
        default="Echodraft is ready to produce your audiobook.", min_length=1, max_length=1000
    )
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


class LocalAiModelCatalogItem(ApiModel):
    model_key: str = Field(alias="modelKey")
    display_name: str = Field(alias="displayName")
    capability: str
    provider: str
    install_type: str = Field(alias="installType")
    required: bool = False
    size_mb: int | None = Field(default=None, alias="sizeMb")
    license_summary: str | None = Field(default=None, alias="licenseSummary")
    license_note: str | None = Field(default=None, alias="licenseNote")
    description: str | None = None
    status: str = "not_installed"
    health: str = "unknown"
    install_path: str | None = Field(default=None, alias="installPath")
    last_verified_at: datetime | None = Field(default=None, alias="lastVerifiedAt")


class LocalAiInstallation(ApiModel):
    id: str
    model_key: str = Field(alias="modelKey")
    display_name: str = Field(alias="displayName")
    capability: str
    provider: str
    version: str | None = None
    install_path: str | None = Field(default=None, alias="installPath")
    status: str
    installed_at: datetime | None = Field(default=None, alias="installedAt")
    last_verified_at: datetime | None = Field(default=None, alias="lastVerifiedAt")
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    license_summary: str | None = Field(default=None, alias="licenseSummary")
    error_message: str | None = Field(default=None, alias="errorMessage")


class LocalAiInstallJob(ApiModel):
    id: str
    job_id: str = Field(alias="jobId")
    model_key: str = Field(alias="modelKey")
    status: str
    progress_percent: int = Field(default=0, alias="progressPercent")
    current_step: str | None = Field(default=None, alias="currentStep")
    logs_path: str | None = Field(default=None, alias="logsPath")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    error_message: str | None = Field(default=None, alias="errorMessage")


class LocalAiInstallRequest(ApiModel):
    confirm_network_download: bool = Field(default=False, alias="confirmNetworkDownload")
    confirm_third_party_license: bool = Field(default=False, alias="confirmThirdPartyLicense")
    confirm_system_install: bool = Field(default=False, alias="confirmSystemInstall")
    repair: bool = False


class LocalAiHealth(ApiModel):
    model_key: str = Field(alias="modelKey")
    status: str
    ready: bool
    message: str
    version: str | None = None
    install_path: str | None = Field(default=None, alias="installPath")
    checked_at: datetime = Field(alias="checkedAt")
    details: dict[str, object] = Field(default_factory=dict)


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
    created_at: datetime | None = Field(default=None, alias="createdAt")


class SegmentRenderComparison(ApiModel):
    segment_id: str = Field(alias="segmentId")
    current_render: SegmentRender | None = Field(default=None, alias="currentRender")
    previous_render: SegmentRender | None = Field(default=None, alias="previousRender")
    changed_fields: list[str] = Field(default_factory=list, alias="changedFields")


class RenderQueueItem(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    chapter_id: str = Field(alias="chapterId")
    segment_id: str = Field(alias="segmentId")
    job_id: str = Field(alias="jobId")
    status: str
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")
    provider: str
    render_key: str | None = Field(default=None, alias="renderKey")
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


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
    created_at: datetime | None = Field(default=None, alias="createdAt")


class ChapterAssemblyRequest(ApiModel):
    render_mode: str = Field(default="speech_only", alias="renderMode")


class AmbienceAsset(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    asset_type: str = Field(default="ambience", alias="assetType")
    asset_path: str = Field(alias="assetPath")
    audio_url: str | None = Field(default=None, alias="audioUrl")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    license_note: str = Field(alias="licenseNote")
    provenance: str


class AmbienceAssetCreate(ApiModel):
    name: str
    asset_type: str = Field(default="ambience", alias="assetType")
    asset_path: str = Field(alias="assetPath")
    duration_ms: int | None = Field(default=None, alias="durationMs")
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
    cue_type: str = Field(default="ambience", alias="cueType")
    start_ms: int = Field(default=0, alias="startMs")
    gain_db: float = Field(alias="gainDb")
    fade_in_ms: int = Field(alias="fadeInMs")
    fade_out_ms: int = Field(alias="fadeOutMs")
    ducking: bool = True
    render_mode: str = Field(default="light", alias="renderMode")
    no_sfx: bool = Field(alias="noSfx")


class AmbienceCueCreate(ApiModel):
    scene_id: str = Field(alias="sceneId")
    asset_id: str | None = Field(default=None, alias="assetId")
    cue_type: str = Field(default="ambience", alias="cueType")
    start_ms: int = Field(default=0, alias="startMs")
    gain_db: float = Field(default=-24.0, alias="gainDb")
    fade_in_ms: int = Field(default=500, alias="fadeInMs")
    fade_out_ms: int = Field(default=500, alias="fadeOutMs")
    ducking: bool = True
    render_mode: str = Field(default="light", alias="renderMode")
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


class IssueApplyActionRequest(ApiModel):
    target_character_id: str | None = Field(default=None, alias="targetCharacterId")
    reason: str | None = None


class IssueApplyActionResult(ApiModel):
    action: str
    character_id: str | None = Field(default=None, alias="characterId")
    source_character_id: str | None = Field(default=None, alias="sourceCharacterId")


class IssueApplyActionResponse(ApiModel):
    issue: Issue
    result: IssueApplyActionResult


class ReadinessCheck(ApiModel):
    id: str
    scope: str
    status: str
    severity: str
    category: str
    title: str
    description: str
    issue_id: str | None = Field(default=None, alias="issueId")
    resolution_status: str | None = Field(default=None, alias="resolutionStatus")
    metadata: dict[str, object] = Field(default_factory=dict)


class ReadinessReport(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    chapter_id: str | None = Field(default=None, alias="chapterId")
    status: str
    score: int
    summary: dict[str, int]
    checks: list[ReadinessCheck]
    created_at: datetime = Field(alias="createdAt")


class ReadinessRunRequest(ApiModel):
    chapter_id: str | None = Field(default=None, alias="chapterId")


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
    # Overrides of the inherited required fields: omitted means "resolve server-side"
    # from the segment's production override / cast / narrator voice and saved direction.
    # Explicitly supplied values act as manual overrides.
    voice_profile_id: str | None = Field(default=None, alias="voiceProfileId")  # type: ignore[assignment]
    direction: DirectionProfile | None = None  # type: ignore[assignment]
    text_content: str | None = Field(default=None, alias="textContent")
    issue_id: str | None = Field(default=None, alias="issueId")


class SegmentPatchResult(ApiModel):
    segment: Segment
    render: SegmentRender
    chapter_render: ChapterRender = Field(alias="chapterRender")


class PatchAttempt(ApiModel):
    id: str
    issue_id: str | None = Field(default=None, alias="issueId")
    segment_id: str = Field(alias="segmentId")
    old_render_id: str | None = Field(default=None, alias="oldRenderId")
    new_render_id: str = Field(alias="newRenderId")
    chapter_render_id: str = Field(alias="chapterRenderId")
    created_at: datetime = Field(alias="createdAt")


class SegmentReviewInspector(ApiModel):
    project_id: str = Field(alias="projectId")
    chapter_id: str = Field(alias="chapterId")
    chapter_title: str | None = Field(default=None, alias="chapterTitle")
    scene_id: str = Field(alias="sceneId")
    segment: Segment
    source_text: str = Field(alias="sourceText")
    canonical_text: str = Field(alias="canonicalText")
    structure: dict[str, object] = Field(default_factory=dict)
    cast: SpeakerAttribution | None = None
    direction: SegmentDirection | None = None
    render_history: list[SegmentRender] = Field(default_factory=list, alias="renderHistory")
    waveform: dict[str, object] = Field(default_factory=dict)
    qa_issues: list[Issue] = Field(default_factory=list, alias="qaIssues")
    comments: list[Comment] = Field(default_factory=list)
    patch_queue: list[PatchAttempt] = Field(default_factory=list, alias="patchQueue")


class ExportBlocker(ApiModel):
    code: str
    severity: str = "blocking"
    message: str
    scope: str
    chapter_id: str | None = Field(default=None, alias="chapterId")
    issue_id: str | None = Field(default=None, alias="issueId")


class ExportQaOutput(ApiModel):
    filename: str
    method: str | None = None
    within_tolerance: bool | None = Field(default=None, alias="withinTolerance")
    lufs_integrated: float | None = Field(default=None, alias="lufsIntegrated")
    true_peak_db: float | None = Field(default=None, alias="truePeakDb")
    rms_dbfs: float | None = Field(default=None, alias="rmsDbfs")
    duration_ms: int = Field(alias="durationMs")
    bytes: int
    sha256: str
    error: str | None = None


class ExportQa(ApiModel):
    target_lufs: float | None = Field(default=None, alias="targetLufs")
    lufs_tolerance: float | None = Field(default=None, alias="lufsTolerance")
    true_peak_ceiling_db: float | None = Field(default=None, alias="truePeakCeilingDb")
    all_within_tolerance: bool | None = Field(default=None, alias="allWithinTolerance")
    outputs: list[ExportQaOutput] = Field(default_factory=list)
    latest_readiness_report: dict[str, object] = Field(
        default_factory=dict, alias="latestReadinessReport"
    )
    open_blocking_issues: list[dict[str, object]] = Field(
        default_factory=list, alias="openBlockingIssues"
    )


class ExportPackage(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    format: str
    status: str
    output_path: str = Field(alias="outputPath")
    manifest_path: str = Field(alias="manifestPath")
    archive_path: str | None = Field(default=None, alias="archivePath")
    download_url: str | None = Field(default=None, alias="downloadUrl")
    audio_variant: str = Field(default="active", alias="audioVariant")
    chapter_count: int = Field(default=0, alias="chapterCount")
    estimated_size_bytes: int = Field(default=0, alias="estimatedSizeBytes")
    checksum: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    manifest_summary: dict[str, object] = Field(default_factory=dict, alias="manifestSummary")
    qa: ExportQa = Field(default_factory=ExportQa)
    blockers: list[ExportBlocker] = Field(default_factory=list)
    created_at: datetime | None = Field(default=None, alias="createdAt")


class ExportRequest(ApiModel):
    format: str = "wav"
    chapter_ids: list[str] = Field(default_factory=list, alias="chapterIds")
    audio_variant: str = Field(default="active", alias="audioVariant")
    title: str | None = None
    author: str | None = None
    album: str | None = None
    publisher: str | None = None
    copyright: str | None = None
    language: str | None = None
    cover_image_path: str | None = Field(default=None, alias="coverImagePath")
    include_retail_sample: bool = Field(default=False, alias="includeRetailSample")


class ExportEstimate(ApiModel):
    project_id: str = Field(alias="projectId")
    format: str
    audio_variant: str = Field(alias="audioVariant")
    chapter_count: int = Field(alias="chapterCount")
    estimated_size_bytes: int = Field(alias="estimatedSizeBytes")
    blockers: list[ExportBlocker] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    m4b_planned: bool = Field(default=False, alias="m4bPlanned")


class ChapterProductionStatus(ApiModel):
    chapter_id: str = Field(alias="chapterId")
    ready: bool
    reason: str | None = None
    total_segments: int = Field(alias="totalSegments")
    current_segments: int = Field(alias="currentSegments")
    active_render: ChapterRender | None = Field(default=None, alias="activeRender")
