from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
from typing import cast
from uuid import uuid4
import wave

from echodraft_db.models import (
    AmbienceAssetRecord,
    AmbienceCueRecord,
    ChapterRecord,
    CharacterRecord,
    SceneRecord,
    SegmentRecord,
    VoiceProfileRecord,
)
from echodraft_domain import (
    AmbienceAsset,
    AmbienceAssetCreate,
    AmbienceCue,
    AmbienceCueCreate,
    AssignVoice,
    Chapter,
    ChapterAssemblyRequest,
    ChapterApproval,
    ChapterApprovalRequest,
    ChapterReviewTimeline,
    ChapterRender,
    ChapterUpdate,
    Character,
    CharacterCreate,
    CharacterMergeRequest,
    CharacterRejectMergeRequest,
    CharacterSplitRequest,
    CharacterUpdate,
    CastingAutoRunRequest,
    CastingDecision,
    CleaningRun,
    Comment,
    CommentCreate,
    ExportPackage,
    ExportEstimate,
    ExportRequest,
    EmbeddingRequest,
    EmbeddingResult,
    DirectionInferenceRunRequest,
    Issue,
    IssueApplyActionRequest,
    IssueApplyActionResponse,
    IssueCreate,
    IssueUpdate,
    Job,
    JobState,
    Project,
    ProjectCreate,
    PronunciationCreate,
    PronunciationEntry,
    ReadinessReport,
    ReadinessRunRequest,
    RenderQueueItem,
    ReparseRequest,
    ReviewTask,
    ReviewTaskUpdate,
    Scene,
    SceneUpdate,
    Segment,
    SegmentDirection,
    SegmentDirectionUpdate,
    SegmentMergeRequest,
    SegmentPatchRequest,
    SegmentPatchResult,
    SegmentReviewInspector,
    SegmentRender,
    SegmentRenderComparison,
    SegmentRenderRequest,
    SegmentRevision,
    SegmentSplitRequest,
    SegmentUpdate,
    SpeakerAttribution,
    SpeakerAttributionRunRequest,
    SpeakerAttributionUpdate,
    SpeakerAttributionUpdateResult,
    SourceDocument,
    SourcePage,
    StructureRequest,
    StructureLockUpdate,
    StructureQuality,
    StructureParserWarning,
    TextCleanlinessIssue,
    TextCleanlinessIssueUpdate,
    VoicePreview,
    VoicePreviewRequest,
    VoiceProfile,
    VoiceCatalogEntry,
    VoiceProfileCreate,
    VoiceSuggestion,
    VoiceProfileUpdate,
    KokoroSetupInstallRequest,
    KokoroSetupStatus,
    LocalAiHealth,
    LocalAiInstallation,
    LocalAiInstallJob,
    LocalAiInstallRequest,
    LocalAiModelCatalogItem,
    LlmExtractionRequest,
    LlmRun,
    TtsSettings,
    TtsSettingsUpdate,
    TtsProviderInfo,
    TtsWorkerStatus,
    TtsTestRequest,
    ProjectProductionSettings,
    ProjectProductionSettingsUpdate,
    SegmentProductionOverride,
    SegmentProductionOverrideUpdate,
    ChapterProductionStatus,
)
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .config import AppSettings
from .confidence import ConfidenceReviewService
from .automatic_casting import AutomaticCastingService
from .voice_catalog import VoiceCatalogService
from .container import AppContainer, build_container
from .logging import configure_logging
from .ingestion import IngestionError, IngestionService, PARSER_VERSION
from .structure import StructureService, chapter_model, revision_model, scene_model, segment_model
from .direction import DirectionService
from .rendering import SegmentRenderer
from .assembly import ChapterAssembler
from .review import ReviewService
from .review_workbench import ReviewWorkbenchService
from .issue_actions import IssueActionService
from .exporting import ExportService
from .production import ProductionService
from .readiness import ReadinessService
from .kokoro_setup import ManagedKokoroSetupService
from .local_ai import LocalAiService
from .local_llm import LocalLlmService
from .speaker_attribution import SpeakerAttributionService

logger = configure_logging()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_environment()
    container = build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            container.orchestrator_pools.shutdown()
            container.tts_worker_manager.stop_all()

    app = FastAPI(title="echodraft API", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3100",
            "http://127.0.0.1:3100",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def artifact_url(project_id: str, absolute_path: str) -> str | None:
        project = container.projects.get(project_id)
        if not project:
            return None
        try:
            relative = Path(absolute_path).resolve().relative_to(Path(project.artifact_path).resolve())
        except ValueError:
            return None
        return f"/api/v1/projects/{project_id}/artifacts/{relative.as_posix()}"

    def segment_render_with_url(project_id: str, render: SegmentRender) -> SegmentRender:
        return render.model_copy(update={"audio_url": artifact_url(project_id, render.audio_path)})

    def chapter_render_with_url(project_id: str, render: ChapterRender) -> ChapterRender:
        path = render.mixed_audio_path or render.speech_path
        return render.model_copy(update={"audio_url": artifact_url(project_id, path)})

    def ambience_asset_model(record: AmbienceAssetRecord) -> AmbienceAsset:
        return AmbienceAsset.model_validate(
            {
                "id": record.id,
                "projectId": record.project_id,
                "name": record.name,
                "assetType": record.asset_type,
                "assetPath": record.asset_path,
                "audioUrl": artifact_url(record.project_id, record.asset_path),
                "durationMs": record.duration_ms,
                "licenseNote": record.license_note,
                "provenance": record.provenance,
            }
        )

    def ambience_cue_model(record: AmbienceCueRecord) -> AmbienceCue:
        return AmbienceCue.model_validate(
            {
                "id": record.id,
                "sceneId": record.scene_id,
                "assetId": record.asset_id,
                "cueType": record.cue_type,
                "startMs": record.start_ms,
                "gainDb": record.gain_db,
                "fadeInMs": record.fade_in_ms,
                "fadeOutMs": record.fade_out_ms,
                "ducking": record.ducking,
                "renderMode": record.render_mode,
                "noSfx": record.no_sfx,
            }
        )

    def wav_duration_ms(path: Path) -> int:
        with wave.open(str(path), "rb") as source:
            if source.getnchannels() < 1:
                raise ValueError("Sound asset WAV has no channels.")
            if source.getnframes() <= 0:
                raise ValueError("Sound asset WAV has no audio frames.")
            return int(source.getnframes() / source.getframerate() * 1000)

    def validate_sound_choice(value: str, allowed: set[str], label: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        if normalized not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported {label}: {value}. Use one of {', '.join(sorted(allowed))}.",
            )
        return normalized

    def _json_list(value: str | None) -> list[object]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    def _name_key(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    def character_model(record: CharacterRecord, voice_profile_id: str | None = None) -> Character:
        return Character.model_validate(
            {
                "id": record.id,
                "projectId": record.project_id,
                "displayName": record.display_name,
                "canonicalName": record.canonical_name,
                "aliases": [str(item) for item in _json_list(record.aliases_json)],
                "traits": [str(item) for item in _json_list(record.traits_json)],
                "firstSeenSourceId": record.first_seen_source_id,
                "firstSeenChapterId": record.first_seen_chapter_id,
                "firstSeenSegmentId": record.first_seen_segment_id,
                "roleType": record.role_type,
                "confidence": record.confidence,
                "notes": record.notes,
                "mergeHistory": [
                    item for item in _json_list(record.merge_history_json) if isinstance(item, dict)
                ],
                "splitHistory": [
                    item for item in _json_list(record.split_history_json) if isinstance(item, dict)
                ],
                "userLocked": record.user_locked,
                "lockReason": record.lock_reason,
                "mergedIntoCharacterId": record.merged_into_character_id,
                "voiceProfileId": voice_profile_id,
            }
        )

    def voice_profile_model(record: VoiceProfileRecord) -> VoiceProfile:
        provider_voice_id = record.provider_voice_id
        catalog_entry = VoiceCatalogService(container).entry(record.voice_catalog_entry_id)
        return VoiceProfile.model_validate(
            {
                "id": record.id,
                "projectId": record.project_id,
                "name": record.name,
                "backend": record.backend,
                "providerVoiceId": provider_voice_id,
                "stylePrompt": record.style_prompt,
                "facets": (
                    catalog_entry.facets
                    if catalog_entry
                    else _voice_facets(record.backend, provider_voice_id)
                ),
                "voiceCatalogEntryId": record.voice_catalog_entry_id,
            }
        )

    def voice_suggestions(character: CharacterRecord) -> list[VoiceSuggestion]:
        traits = [str(item) for item in _json_list(character.traits_json)]
        representative_lines = container.speaker_attributions.character_segment_texts(
            character.id, limit=1
        )
        sample_text = representative_lines[0] if representative_lines else _fallback_audition_line(character)
        suggestions: list[VoiceSuggestion] = []
        for voice in container.casting.voices(character.project_id):
            facets = _voice_facets(voice.backend, voice.provider_voice_id)
            haystack = " ".join(
                [voice.name, voice.backend, voice.provider_voice_id, voice.style_prompt or "", *facets]
            ).casefold()
            matched = [trait for trait in traits if _voice_matches_trait(trait, haystack)]
            evidence = [
                f"Matched {trait} in voice metadata."
                for trait in matched
            ]
            if facets:
                evidence.append(f"Derived voice facets: {', '.join(facets)}.")
            if representative_lines:
                evidence.append("Representative character line selected for audition.")
            if not evidence:
                evidence.append("No explicit trait match; included as an available project voice.")
            score = round(len(matched) / max(1, len(traits)), 3)
            suggestions.append(
                VoiceSuggestion(
                    voiceProfileId=voice.id,
                    name=voice.name,
                    providerVoiceId=voice.provider_voice_id,
                    backend=voice.backend,
                    score=score,
                    matchedTraits=matched,
                    facets=facets,
                    evidence=evidence,
                    sampleText=sample_text,
                )
            )
        return sorted(
            suggestions,
            key=lambda item: (-item.score, -len(item.matched_traits), item.name.casefold()),
        )

    def _voice_matches_trait(trait: str, haystack: str) -> bool:
        value = trait.split(":", 1)[-1].casefold()
        synonyms = {
            "feminine": ["feminine", "female", "woman", "girl"],
            "masculine": ["masculine", "male", "man", "boy"],
            "young": ["young", "youth", "teen"],
            "old": ["old", "older", "elder"],
        }
        return any(term in haystack for term in [value, *synonyms.get(value, [])])

    def _fallback_audition_line(character: CharacterRecord) -> str:
        return (
            f"{character.display_name}: This audition line should match the character's "
            "observed age, accent, role, and vocal traits."
        )

    def _voice_facets(backend: str, provider_voice_id: str) -> list[str]:
        tokens = [token for token in re.split(r"[^a-z0-9]+", provider_voice_id.casefold()) if token]
        facets: list[str] = []
        if backend == "kokoro" and tokens:
            prefix = tokens[0]
            kokoro_prefixes = {
                "af": ["gender:feminine", "accent:american", "locale:american"],
                "am": ["gender:masculine", "accent:american", "locale:american"],
                "bf": ["gender:feminine", "accent:british", "locale:british"],
                "bm": ["gender:masculine", "accent:british", "locale:british"],
            }
            facets.extend(kokoro_prefixes.get(prefix, []))
        token_facets = {
            "female": "gender:feminine",
            "feminine": "gender:feminine",
            "woman": "gender:feminine",
            "male": "gender:masculine",
            "masculine": "gender:masculine",
            "man": "gender:masculine",
            "irish": "accent:irish",
            "american": "accent:american",
            "british": "accent:british",
            "english": "accent:english",
            "scottish": "accent:scottish",
            "french": "accent:french",
            "spanish": "accent:spanish",
            "indian": "accent:indian",
            "young": "age:young",
            "old": "age:old",
            "elder": "age:old",
            "older": "age:old",
        }
        facets.extend(token_facets[token] for token in tokens if token in token_facets)
        cleaned: list[str] = []
        seen: set[str] = set()
        for facet in facets:
            if facet not in seen:
                cleaned.append(facet)
                seen.add(facet)
        return cleaned

    @app.middleware("http")
    async def request_logging(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))
        try:
            response = await call_next(request)
        except Exception as error:
            logger.exception(
                "request.failed",
                extra={"request_id": request_id, "error": str(error)},
            )
            raise
        response.headers["x-request-id"] = request_id
        logger.info("request.completed", extra={"request_id": request_id})
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "local-first"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready", "storage": str(resolved_settings.artifact_root)}

    @app.get("/api/v1/settings/tts", response_model=TtsSettings)
    def get_tts_settings(request: Request) -> TtsSettings:
        container: AppContainer = request.app.state.container
        return container.tts_settings.status()

    @app.get("/api/v1/settings/tts/providers", response_model=list[TtsProviderInfo])
    def get_tts_providers(request: Request) -> list[TtsProviderInfo]:
        container: AppContainer = request.app.state.container
        return [
            TtsProviderInfo.model_validate(provider)
            for provider in container.tts_settings.providers()
        ]

    @app.get("/api/v1/settings/tts/worker", response_model=TtsWorkerStatus)
    def get_tts_worker_status(request: Request) -> TtsWorkerStatus:
        container: AppContainer = request.app.state.container
        current = container.tts_settings.load()
        return container.tts_worker_manager.status(
            provider=current.provider, setup_mode=current.setup_mode
        )

    @app.put("/api/v1/settings/tts", response_model=TtsSettings)
    def save_tts_settings(payload: TtsSettingsUpdate, request: Request) -> TtsSettings:
        container: AppContainer = request.app.state.container
        try:
            saved = container.tts_settings.save(payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        container.tts_worker_manager.stop_all()
        container.tts_adapter = container.tts_settings.adapter(
            worker_manager=container.tts_worker_manager
        )
        return saved

    @app.post("/api/v1/settings/tts/test", response_model=TtsSettings)
    def test_tts_settings(payload: TtsTestRequest, request: Request) -> TtsSettings:
        container: AppContainer = request.app.state.container
        current = container.tts_settings.status()
        if not current.ready:
            raise HTTPException(status_code=422, detail=current.message or "TTS is not ready.")
        voice = payload.voice_id or (current.available_voices[0] if current.available_voices else None)
        if not voice:
            raise HTTPException(status_code=422, detail="No local voice is available for a test.")
        resolved_settings.artifact_root.mkdir(parents=True, exist_ok=True)
        probe = resolved_settings.artifact_root / "tts-test.wav"
        try:
            from echodraft_domain import DirectionProfile

            container.tts_adapter.preview(
                payload.text, voice, probe, DirectionProfile(scopeType="system", scopeId="tts-test")
            )
            probe.unlink(missing_ok=True)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return current

    @app.get("/api/v1/settings/tts/kokoro/setup", response_model=KokoroSetupStatus)
    def get_kokoro_setup(request: Request) -> KokoroSetupStatus:
        container: AppContainer = request.app.state.container
        return ManagedKokoroSetupService(
            container.settings, container.tts_settings, container.jobs_repository
        ).status()

    @app.post("/api/v1/settings/tts/kokoro/setup/install", response_model=Job)
    def install_kokoro_setup(payload: KokoroSetupInstallRequest, request: Request) -> Job:
        if not payload.confirm_network_download or not payload.confirm_third_party_license:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Confirm the local network download and third-party Kokoro package/model "
                    "setup before installing."
                ),
            )
        container: AppContainer = request.app.state.container

        def operation(job_id: str) -> None:
            service = ManagedKokoroSetupService(
                container.settings, container.tts_settings, container.jobs_repository
            )
            service.install(job_id, repair=payload.repair)
            container.tts_worker_manager.stop_all()
            container.tts_adapter = container.tts_settings.adapter(
                worker_manager=container.tts_worker_manager
            )

        return container.jobs.submit_with_job(
            "kokoro_setup", operation, project_id=None, target_id="managed_onnx"
        )

    @app.get("/api/v1/local-ai/catalog", response_model=list[LocalAiModelCatalogItem])
    def get_local_ai_catalog(request: Request) -> list[LocalAiModelCatalogItem]:
        return LocalAiService(request.app.state.container).catalog()

    @app.get("/api/v1/local-ai/installed", response_model=list[LocalAiInstallation])
    def get_local_ai_installed(request: Request) -> list[LocalAiInstallation]:
        return LocalAiService(request.app.state.container).installations()

    @app.post("/api/v1/local-ai/models/{model_key}/install", response_model=Job, status_code=202)
    def install_local_ai_model(
        model_key: str, payload: LocalAiInstallRequest, request: Request
    ) -> Job:
        container: AppContainer = request.app.state.container
        service = LocalAiService(container)
        try:
            service.health(model_key)
            service.validate_install_request(model_key, payload)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Local AI catalog item not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return container.jobs.submit_with_job(
            "local_ai.install",
            lambda job_id: LocalAiService(container).install(job_id, model_key, payload),
            project_id=None,
            target_id=model_key,
        )

    @app.post(
        "/api/v1/local-ai/models/{model_key}/verify", response_model=LocalAiInstallation
    )
    def verify_local_ai_model(model_key: str, request: Request) -> LocalAiInstallation:
        try:
            return LocalAiService(request.app.state.container).verify(model_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Local AI catalog item not found") from error

    @app.delete("/api/v1/local-ai/models/{model_key}", status_code=204)
    def uninstall_local_ai_model(model_key: str, request: Request) -> None:
        try:
            LocalAiService(request.app.state.container).uninstall(model_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Local AI catalog item not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v1/local-ai/models/{model_key}/health", response_model=LocalAiHealth)
    def get_local_ai_health(model_key: str, request: Request) -> LocalAiHealth:
        try:
            return LocalAiService(request.app.state.container).health(model_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Local AI catalog item not found") from error

    @app.get("/api/v1/local-ai/jobs/{job_id}", response_model=LocalAiInstallJob)
    def get_local_ai_install_job(job_id: str, request: Request) -> LocalAiInstallJob:
        install_job = LocalAiService(request.app.state.container).install_job(job_id)
        if not install_job:
            raise HTTPException(status_code=404, detail="Local AI install job not found")
        return install_job

    @app.get("/api/v1/local-llm/ollama/models")
    def list_ollama_models(request: Request) -> list[dict[str, object]]:
        try:
            return LocalLlmService(request.app.state.container).installed_models()
        except ValueError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/v1/local-llm/embeddings", response_model=EmbeddingResult)
    def create_embedding(payload: EmbeddingRequest, request: Request) -> EmbeddingResult:
        try:
            return LocalLlmService(request.app.state.container).embed(payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/local-llm/extractions",
        response_model=Job,
        status_code=202,
    )
    def create_llm_extraction(
        project_id: str, payload: LlmExtractionRequest, request: Request
    ) -> Job:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        def operation(job_id: str) -> None:
            LocalLlmService(container).extract(project_id, payload, job_id)

        return container.jobs.submit_with_job(
            "local_llm.extract",
            operation,
            project_id=project_id,
        )

    @app.get("/api/v1/projects/{project_id}/llm-runs", response_model=list[LlmRun])
    def list_llm_runs(project_id: str, request: Request) -> list[LlmRun]:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.llm_runs.list_for_project(project_id)

    @app.get("/api/v1/llm-runs/{run_id}", response_model=LlmRun)
    def get_llm_run(run_id: str, request: Request) -> LlmRun:
        container: AppContainer = request.app.state.container
        run = container.llm_runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="LLM run not found")
        return run

    @app.get("/api/v1/projects/{project_id}/artifacts/{artifact_path:path}")
    def get_artifact(project_id: str, artifact_path: str, request: Request) -> FileResponse:
        project = request.app.state.container.projects.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        root = Path(project.artifact_path).resolve()
        target = (root / artifact_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(target)

    @app.post("/api/v1/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
    def create_project(payload: ProjectCreate, request: Request) -> Project:
        app_container: AppContainer = request.app.state.container
        project_id_hint = f"proj_{uuid4().hex[:16]}"
        artifact_path = app_container.artifacts.create_project_layout(project_id_hint)
        try:
            project = app_container.projects.create(payload, str(artifact_path), project_id_hint)
        except Exception:
            app_container.artifacts.remove_project_layout(project_id_hint)
            raise
        logger.info("project.created", extra={"project_id": project.id})
        return project

    @app.get("/api/v1/projects", response_model=list[Project])
    def list_projects(request: Request) -> list[Project]:
        app_container: AppContainer = request.app.state.container
        return app_container.projects.list()

    @app.get("/api/v1/jobs/{job_id}", response_model=Job)
    def get_job(job_id: str, request: Request) -> Job:
        app_container: AppContainer = request.app.state.container
        job = app_container.jobs_repository.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/api/v1/projects/{project_id}/jobs", response_model=list[Job])
    def list_project_jobs(
        project_id: str,
        request: Request,
        job_type: str | None = None,
        job_status: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[Job]:
        app_container: AppContainer = request.app.state.container
        if not app_container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        statuses: list[JobState] | None = None
        if job_status:
            try:
                statuses = [
                    JobState(item.strip()) for item in job_status.split(",") if item.strip()
                ]
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Invalid job status filter") from error
        return app_container.jobs_repository.list_for_project(
            project_id, job_type=job_type, statuses=statuses, limit=limit
        )

    @app.get("/api/v1/events")
    def stream_job_events(
        request: Request,
        job_id: str = Query(..., alias="jobId"),
        after: int = Query(0, ge=0),
    ) -> StreamingResponse:
        app_container: AppContainer = request.app.state.container
        if not app_container.jobs_repository.get(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        last_event_id = _event_cursor(request.headers.get("last-event-id"), after)

        def event_stream() -> Iterable[str]:
            for event in app_container.orchestrator_repository.events_for_job(
                job_id, after_event_id=last_event_id
            ):
                payload = {
                    "jobId": event.job_id,
                    "projectId": event.project_id,
                    "type": event.type,
                    "stage": event.stage,
                    "scope": json.loads(event.scope_json or "{}"),
                    "payload": json.loads(event.payload_json or "{}"),
                    "ts": event.ts.isoformat(),
                }
                yield f"id: {event.event_id}\n"
                yield f"event: {event.type}\n"
                yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
            yield ": heartbeat\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    @app.post("/api/v1/projects/{project_id}/source/import", response_model=Job, status_code=202)
    async def import_source(
        project_id: str,
        request: Request,
        file: UploadFile = File(...),
        rights_acknowledged: bool = Form(..., alias="rightsAcknowledged"),
        parser_version: str = Form(PARSER_VERSION, alias="parserVersion"),
    ) -> Job:
        if not rights_acknowledged:
            raise HTTPException(
                status_code=422, detail="Rights acknowledgement is required for import."
            )
        container: AppContainer = request.app.state.container
        service = IngestionService(container)
        try:
            source_id = service.stage(
                project_id,
                file.filename or "manuscript.txt",
                file.content_type,
                await file.read(),
                parser_version,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Project not found") from None
        except IngestionError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        source = container.sources.latest(project_id)
        assert source
        def operation(job_id: str) -> None:
            container.jobs_repository.set_progress(
                job_id,
                {
                    "phase": "normalizing",
                    "message": "Normalizing manuscript locally.",
                },
            )
            service.process(
                source_id,
                project_id,
                source.original_filename,
                source.mime_type,
                parser_version,
                Path(source.original_path),
            )
            container.jobs_repository.set_progress(
                job_id,
                {
                    "phase": "completed",
                    "message": "Manuscript import completed.",
                },
            )

        job = container.jobs.submit_with_job(
            "source.import",
            operation,
            project_id,
        )
        return job

    @app.post("/api/v1/projects/{project_id}/source/reparse", response_model=Job, status_code=202)
    def reparse_source(project_id: str, payload: ReparseRequest, request: Request) -> Job:
        container: AppContainer = request.app.state.container
        previous = container.sources.latest(project_id)
        if not previous:
            raise HTTPException(status_code=404, detail="No source document found")
        service = IngestionService(container)
        try:
            source_id = service.stage(
                project_id,
                previous.original_filename,
                previous.mime_type,
                Path(previous.original_path).read_bytes(),
                payload.parser_version,
            )
        except IngestionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        source = container.sources.latest(project_id)
        assert source
        return container.jobs.submit(
            "source.reparse",
            lambda: service.process(
                source_id,
                project_id,
                source.original_filename,
                source.mime_type,
                payload.parser_version,
                Path(source.original_path),
            ),
            project_id,
        )

    @app.get("/api/v1/projects/{project_id}/source", response_model=SourceDocument)
    def get_source(project_id: str, request: Request) -> SourceDocument:
        container: AppContainer = request.app.state.container
        source = container.sources.latest(project_id)
        if not source:
            raise HTTPException(status_code=404, detail="No source document found")
        if source.canonical_path and Path(source.canonical_path).exists():
            source.preview = Path(source.canonical_path).read_text(encoding="utf-8")[:6000]
        return source

    @app.get("/api/v1/sources/{source_id}", response_model=SourceDocument)
    def get_source_by_id(source_id: str, request: Request) -> SourceDocument:
        container: AppContainer = request.app.state.container
        source = container.sources.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source document not found")
        if source.canonical_path and Path(source.canonical_path).exists():
            source.preview = Path(source.canonical_path).read_text(encoding="utf-8")[:6000]
        return source

    def source_page_with_url(source: SourceDocument, page: SourcePage) -> SourcePage:
        return page.model_copy(
            update={
                "image_url": artifact_url(source.project_id, page.image_path)
                if page.image_path
                else None
            }
        )

    @app.get("/api/v1/sources/{source_id}/pages", response_model=list[SourcePage])
    def list_source_pages(source_id: str, request: Request) -> list[SourcePage]:
        container: AppContainer = request.app.state.container
        source = container.sources.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source document not found")
        return [
            source_page_with_url(source, page)
            for page in container.source_artifacts.pages(source_id)
        ]

    @app.get("/api/v1/sources/{source_id}/pages/{page_number}", response_model=SourcePage)
    def get_source_page(source_id: str, page_number: int, request: Request) -> SourcePage:
        container: AppContainer = request.app.state.container
        source = container.sources.get(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source document not found")
        page = container.source_artifacts.page(source_id, page_number)
        if not page:
            raise HTTPException(status_code=404, detail="Source page not found")
        return source_page_with_url(source, page)

    @app.get(
        "/api/v1/sources/{source_id}/cleaning-issues",
        response_model=list[TextCleanlinessIssue],
    )
    def list_cleaning_issues(
        source_id: str, request: Request
    ) -> list[TextCleanlinessIssue]:
        container: AppContainer = request.app.state.container
        if not container.sources.get(source_id):
            raise HTTPException(status_code=404, detail="Source document not found")
        return container.source_artifacts.cleanliness_issues(source_id)

    @app.get(
        "/api/v1/sources/{source_id}/cleaning-runs",
        response_model=list[CleaningRun],
    )
    def list_cleaning_runs(source_id: str, request: Request) -> list[CleaningRun]:
        container: AppContainer = request.app.state.container
        if not container.sources.get(source_id):
            raise HTTPException(status_code=404, detail="Source document not found")
        return container.source_artifacts.cleaning_runs(source_id)

    @app.patch(
        "/api/v1/cleaning-issues/{issue_id}", response_model=TextCleanlinessIssue
    )
    def update_cleaning_issue(
        issue_id: str, payload: TextCleanlinessIssueUpdate, request: Request
    ) -> TextCleanlinessIssue:
        container: AppContainer = request.app.state.container
        issue = container.source_artifacts.update_cleanliness_issue(
            issue_id, payload.status, payload.resolved_by_user
        )
        if not issue:
            raise HTTPException(status_code=404, detail="Cleaning issue not found")
        return issue

    @app.post(
        "/api/v1/projects/{project_id}/structure/extract", response_model=Job, status_code=202
    )
    def extract_structure(project_id: str, payload: StructureRequest, request: Request) -> Job:
        container: AppContainer = request.app.state.container
        service = StructureService(container)
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.jobs.submit_with_job(
            "structure.extract",
            lambda job_id: service.extract(project_id, payload.max_segment_chars, job_id=job_id),
            project_id,
        )

    @app.get("/api/v1/projects/{project_id}/chapters", response_model=list[Chapter])
    def list_chapters(project_id: str, request: Request) -> list[Chapter]:
        return [
            chapter_model(item)
            for item in request.app.state.container.structure.chapters(project_id)
        ]

    @app.get(
        "/api/v1/projects/{project_id}/structure-warnings",
        response_model=list[StructureParserWarning],
    )
    def list_structure_warnings(
        project_id: str, request: Request
    ) -> list[StructureParserWarning]:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.structure.warnings(project_id)

    @app.get(
        "/api/v1/projects/{project_id}/structure/quality",
        response_model=StructureQuality,
    )
    def get_structure_quality(project_id: str, request: Request) -> StructureQuality:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return StructureService(container).quality(project_id)

    @app.get("/api/v1/chapters/{chapter_id}", response_model=Chapter)
    def get_chapter(chapter_id: str, request: Request) -> Chapter:
        record = request.app.state.container.structure.chapter(chapter_id)
        if not record:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return chapter_model(record)

    @app.patch("/api/v1/chapters/{chapter_id}", response_model=Chapter)
    def update_chapter(
        chapter_id: str, payload: ChapterUpdate, request: Request
    ) -> Chapter:
        container: AppContainer = request.app.state.container
        record = container.structure.update_chapter(chapter_id, payload.title, payload.status)
        if not record:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return chapter_model(record)

    @app.get("/api/v1/chapters/{chapter_id}/scenes", response_model=list[Scene])
    def list_scenes(chapter_id: str, request: Request) -> list[Scene]:
        return [
            scene_model(item) for item in request.app.state.container.structure.scenes(chapter_id)
        ]

    @app.patch("/api/v1/scenes/{scene_id}", response_model=Scene)
    def update_scene(scene_id: str, payload: SceneUpdate, request: Request) -> Scene:
        container: AppContainer = request.app.state.container
        record = container.structure.update_scene(scene_id, payload.status)
        if not record:
            raise HTTPException(status_code=404, detail="Scene not found")
        return scene_model(record)

    @app.get("/api/v1/scenes/{scene_id}/segments", response_model=list[Segment])
    def list_segments(scene_id: str, request: Request) -> list[Segment]:
        return [
            segment_model(item) for item in request.app.state.container.structure.segments(scene_id)
        ]

    @app.patch("/api/v1/segments/{segment_id}", response_model=Segment)
    def update_segment(segment_id: str, payload: SegmentUpdate, request: Request) -> Segment:
        record = request.app.state.container.structure.update_segment(
            segment_id, payload.text_content
        )
        if not record:
            raise HTTPException(status_code=404, detail="Segment not found")
        return segment_model(record)

    @app.put(
        "/api/v1/structure-locks/{scope_type}/{scope_id}",
        response_model=Chapter | Scene | Segment,
    )
    def update_structure_lock(
        scope_type: str, scope_id: str, payload: StructureLockUpdate, request: Request
    ) -> Chapter | Scene | Segment:
        container: AppContainer = request.app.state.container
        record = container.structure.set_lock(scope_type, scope_id, payload.locked, payload.reason)
        if not record:
            raise HTTPException(status_code=404, detail="Structure item not found")
        if scope_type == "chapter":
            return chapter_model(cast(ChapterRecord, record))
        if scope_type == "scene":
            return scene_model(cast(SceneRecord, record))
        return segment_model(cast(SegmentRecord, record))

    @app.post("/api/v1/segments/{segment_id}/split", response_model=Segment)
    def split_segment(
        segment_id: str, payload: SegmentSplitRequest, request: Request
    ) -> Segment:
        try:
            record = request.app.state.container.structure.split_segment(
                segment_id, payload.split_offset
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not record:
            raise HTTPException(status_code=404, detail="Segment not found")
        return segment_model(record)

    @app.post("/api/v1/segments/{segment_id}/merge", response_model=Segment)
    def merge_segment(
        segment_id: str, payload: SegmentMergeRequest, request: Request
    ) -> Segment:
        try:
            record = request.app.state.container.structure.merge_segments(
                segment_id, payload.next_segment_id
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not record:
            raise HTTPException(status_code=404, detail="Segment not found")
        return segment_model(record)

    @app.get("/api/v1/segments/{segment_id}/revisions", response_model=list[SegmentRevision])
    def list_segment_revisions(segment_id: str, request: Request) -> list[SegmentRevision]:
        return [
            revision_model(item)
            for item in request.app.state.container.structure.revisions(segment_id)
        ]

    @app.get(
        "/api/v1/projects/{project_id}/production-settings",
        response_model=ProjectProductionSettings,
    )
    def get_production_settings(project_id: str, request: Request) -> ProjectProductionSettings:
        try:
            return ProductionService(request.app.state.container).settings(project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put(
        "/api/v1/projects/{project_id}/production-settings",
        response_model=ProjectProductionSettings,
    )
    def update_production_settings(
        project_id: str, payload: ProjectProductionSettingsUpdate, request: Request
    ) -> ProjectProductionSettings:
        try:
            return ProductionService(request.app.state.container).update_settings(
                project_id,
                payload.narrator_voice_profile_id,
                payload.default_direction,
                payload.casting_style_preset,
                payload.auto_cast_enabled,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/segments/{segment_id}/production-override",
        response_model=SegmentProductionOverride,
    )
    def get_segment_override(
        project_id: str, segment_id: str, request: Request
    ) -> SegmentProductionOverride:
        try:
            return ProductionService(request.app.state.container).override(project_id, segment_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put(
        "/api/v1/projects/{project_id}/segments/{segment_id}/production-override",
        response_model=SegmentProductionOverride,
    )
    def update_segment_override(
        project_id: str,
        segment_id: str,
        payload: SegmentProductionOverrideUpdate,
        request: Request,
    ) -> SegmentProductionOverride:
        try:
            return ProductionService(request.app.state.container).update_override(
                project_id, segment_id, payload.voice_profile_id, payload.direction
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/segment-directions",
        response_model=list[SegmentDirection],
    )
    def list_segment_directions(project_id: str, request: Request) -> list[SegmentDirection]:
        try:
            return DirectionService(request.app.state.container).list_segment_directions(project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/segments/{segment_id}/direction",
        response_model=SegmentDirection,
    )
    def get_segment_direction(
        project_id: str, segment_id: str, request: Request
    ) -> SegmentDirection:
        try:
            return DirectionService(request.app.state.container).segment_direction(
                project_id, segment_id
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put(
        "/api/v1/projects/{project_id}/segments/{segment_id}/direction",
        response_model=SegmentDirection,
    )
    def update_segment_direction(
        project_id: str,
        segment_id: str,
        payload: SegmentDirectionUpdate,
        request: Request,
    ) -> SegmentDirection:
        try:
            return DirectionService(request.app.state.container).update_segment_direction(
                project_id, segment_id, payload.direction, payload.user_locked
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/directions/infer",
        response_model=Job,
        status_code=202,
    )
    def infer_segment_directions(
        project_id: str,
        request: Request,
        payload: DirectionInferenceRunRequest = Body(default_factory=DirectionInferenceRunRequest),
    ) -> Job:
        container: AppContainer = request.app.state.container
        service = DirectionService(container)
        try:
            service.list_segment_directions(project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        def run(job_id: str) -> None:
            service.infer_segment_directions(
                project_id,
                job_id,
                use_local_llm=payload.use_local_llm,
                model=payload.model,
            )

        return container.jobs.submit_with_job(
            "directions.infer",
            run,
            project_id,
        )

    @app.get("/api/v1/projects/{project_id}/characters", response_model=list[Character])
    def list_characters(project_id: str, request: Request) -> list[Character]:
        assignments = request.app.state.container.casting.character_voice_assignments(project_id)
        return [
            character_model(x, assignments.get(x.id))
            for x in request.app.state.container.casting.characters(project_id)
        ]

    @app.post("/api/v1/projects/{project_id}/characters", response_model=Character, status_code=201)
    def create_character(project_id: str, payload: CharacterCreate, request: Request) -> Character:
        x = request.app.state.container.casting.create_character(
            project_id=project_id,
            name=payload.display_name,
            aliases=payload.aliases,
            role=payload.role_type,
            confidence=payload.confidence,
            notes=payload.notes,
            canonical_name=payload.canonical_name,
            traits=payload.traits,
            first_seen_source_id=payload.first_seen_source_id,
            first_seen_chapter_id=payload.first_seen_chapter_id,
            first_seen_segment_id=payload.first_seen_segment_id,
        )
        return character_model(x)

    @app.patch("/api/v1/characters/{character_id}", response_model=Character)
    def update_character(
        character_id: str, payload: CharacterUpdate, request: Request
    ) -> Character:
        update_voice = "voice_profile_id" in payload.model_fields_set
        try:
            x = request.app.state.container.casting.update_character(
                character_id,
                display_name=payload.display_name,
                canonical_name=payload.canonical_name,
                aliases=payload.aliases,
                traits=payload.traits,
                role_type=payload.role_type,
                confidence=payload.confidence,
                notes=payload.notes,
                user_locked=payload.user_locked,
                lock_reason=payload.lock_reason,
                voice_profile_id=payload.voice_profile_id,
                update_voice=update_voice,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not x:
            raise HTTPException(status_code=404, detail="Character not found")
        voice_id = request.app.state.container.casting.character_voice_assignment(character_id)
        return character_model(x, voice_id)

    @app.get(
        "/api/v1/characters/{character_id}/voice-suggestions",
        response_model=list[VoiceSuggestion],
    )
    def suggest_character_voices(character_id: str, request: Request) -> list[VoiceSuggestion]:
        character = request.app.state.container.casting.character(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        return voice_suggestions(character)

    @app.post("/api/v1/characters/{character_id}/merge", response_model=Character)
    def merge_character(
        character_id: str, payload: CharacterMergeRequest, request: Request
    ) -> Character:
        try:
            x = request.app.state.container.casting.merge_characters(
                character_id, payload.source_character_id, payload.reason
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        voice_id = request.app.state.container.casting.character_voice_assignment(character_id)
        return character_model(x, voice_id)

    @app.post("/api/v1/characters/{character_id}/reject-merge", response_model=Character)
    def reject_merge(
        character_id: str, payload: CharacterRejectMergeRequest, request: Request
    ) -> Character:
        container: AppContainer = request.app.state.container
        character = container.casting.character(character_id)
        if not character:
            raise HTTPException(status_code=404, detail="Character not found")
        decision = container.cast_merge_decisions.record(
            character.project_id,
            character.display_name,
            payload.candidate_name,
            "rejected",
            payload.reason,
        )
        if decision is None:
            raise HTTPException(
                status_code=422,
                detail="Cannot reject a merge between a character and itself.",
            )
        # Resolve any open "possible duplicate" issue linking this pair so the
        # rejection actually clears the reviewer's queue.
        candidate_key = _name_key(payload.candidate_name)
        character_key = _name_key(character.display_name)
        for issue in container.review.issues(character.project_id, status="open"):
            metadata = json.loads(issue.metadata_json or "{}")
            if metadata.get("code") != "cast.possible_duplicate":
                continue
            if _name_key(str(metadata.get("candidateName", ""))) != candidate_key:
                continue
            possible = [
                _name_key(str(name))
                for name in metadata.get("possibleMatches", [])
                if isinstance(name, str)
            ]
            if character_key in possible or not possible:
                container.review.update_issue(issue.id, status="resolved", severity=None)
        voice_id = container.casting.character_voice_assignment(character_id)
        return character_model(character, voice_id)

    @app.post("/api/v1/characters/{character_id}/split", response_model=Character, status_code=201)
    def split_character(
        character_id: str, payload: CharacterSplitRequest, request: Request
    ) -> Character:
        try:
            x = request.app.state.container.casting.split_character(
                character_id, payload.display_name, payload.aliases, payload.traits, payload.reason
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return character_model(x)

    @app.get(
        "/api/v1/projects/{project_id}/speaker-attributions",
        response_model=list[SpeakerAttribution],
    )
    def list_speaker_attributions(
        project_id: str, request: Request, status: str | None = None
    ) -> list[SpeakerAttribution]:
        try:
            return SpeakerAttributionService(request.app.state.container).list_attributions(
                project_id, status
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/speaker-attributions/run",
        response_model=Job,
        status_code=202,
    )
    def run_speaker_attribution(
        project_id: str,
        request: Request,
        payload: SpeakerAttributionRunRequest | None = None,
    ) -> Job:
        container: AppContainer = request.app.state.container
        service = SpeakerAttributionService(container)
        options = payload or SpeakerAttributionRunRequest()
        try:
            service.list_attributions(project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        def run(job_id: str) -> None:
            service.generate(
                project_id,
                use_local_llm=options.use_local_llm,
                model=options.model,
                job_id=job_id,
            )

        return container.jobs.submit_with_job(
            "speaker_attribution.run",
            run,
            project_id,
        )

    @app.patch(
        "/api/v1/speaker-attributions/{attribution_id}",
        response_model=SpeakerAttributionUpdateResult,
    )
    def update_speaker_attribution(
        attribution_id: str, payload: SpeakerAttributionUpdate, request: Request
    ) -> SpeakerAttributionUpdateResult:
        try:
            return SpeakerAttributionService(request.app.state.container).update(
                attribution_id,
                character_id=payload.character_id,
                update_character="character_id" in payload.model_fields_set,
                speaker_name=payload.speaker_name,
                status=payload.status,
                user_locked=payload.user_locked,
            )
        except ValueError as error:
            message = str(error)
            raise HTTPException(
                status_code=404 if "not found" in message.casefold() else 422,
                detail=message,
            ) from error

    @app.get("/api/v1/projects/{project_id}/voices", response_model=list[VoiceProfile])
    def list_voices(project_id: str, request: Request) -> list[VoiceProfile]:
        return [
            voice_profile_model(x)
            for x in request.app.state.container.casting.voices(project_id)
        ]

    @app.get("/api/v1/voice-catalog", response_model=list[VoiceCatalogEntry])
    def list_voice_catalog(request: Request) -> list[VoiceCatalogEntry]:
        return VoiceCatalogService(request.app.state.container).entries()

    @app.post(
        "/api/v1/projects/{project_id}/casting/auto-run",
        response_model=Job,
        status_code=202,
    )
    def run_automatic_casting(
        project_id: str,
        payload: CastingAutoRunRequest,
        request: Request,
    ) -> Job:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found.")
        service = AutomaticCastingService(container)

        def run(job_id: str) -> None:
            service.auto_cast(
                project_id,
                style_preset=payload.casting_style_preset,
                scope=payload.scope,
                job_id=job_id,
            )

        return container.jobs.submit_with_job(
            "casting.auto_run",
            run,
            project_id,
        )

    @app.get(
        "/api/v1/characters/{character_id}/casting-decision",
        response_model=CastingDecision,
    )
    def get_casting_decision(character_id: str, request: Request) -> CastingDecision:
        decision = AutomaticCastingService(request.app.state.container).decision(character_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Casting decision not found.")
        return decision

    @app.post(
        "/api/v1/voice-catalog/audition-jobs",
        response_model=Job,
        status_code=202,
    )
    def audition_voice_catalog(request: Request) -> Job:
        container: AppContainer = request.app.state.container
        service = VoiceCatalogService(container)

        def run(job_id: str) -> None:
            service.audition_backfill(job_id)

        return container.jobs.submit_with_job(
            "voice_catalog.audition",
            run,
            project_id=None,
        )

    @app.post("/api/v1/projects/{project_id}/voices", response_model=VoiceProfile, status_code=201)
    def create_voice(
        project_id: str, payload: VoiceProfileCreate, request: Request
    ) -> VoiceProfile:
        x = request.app.state.container.casting.create_voice(
            project_id, payload.name, payload.backend, payload.provider_voice_id, payload.style_prompt
        )
        return voice_profile_model(x)

    @app.patch("/api/v1/voices/{voice_id}", response_model=VoiceProfile)
    def update_voice(voice_id: str, payload: VoiceProfileUpdate, request: Request) -> VoiceProfile:
        x = request.app.state.container.casting.update_voice(
            voice_id, payload.name, payload.provider_voice_id, payload.style_prompt
        )
        if not x:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        return voice_profile_model(x)

    @app.delete("/api/v1/voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_voice(voice_id: str, request: Request) -> Response:
        try:
            deleted = request.app.state.container.casting.delete_voice(voice_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/v1/characters/{character_id}/assign-voice", status_code=200)
    def assign_voice(character_id: str, payload: AssignVoice, request: Request) -> dict[str, str]:
        try:
            decision = AutomaticCastingService(
                request.app.state.container
            ).override_character_voice(
                character_id,
                payload.voice_profile_id,
                lock_assignment=payload.lock_assignment,
                allow_narrator_reuse=payload.allow_narrator_reuse,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        response = {"status": "assigned"}
        if decision:
            response["castingDecisionId"] = decision.id
        return response

    @app.get(
        "/api/v1/projects/{project_id}/pronunciations", response_model=list[PronunciationEntry]
    )
    def list_pronunciations(project_id: str, request: Request) -> list[PronunciationEntry]:
        return [
            PronunciationEntry.model_validate(
                {
                    "id": x.id,
                    "projectId": x.project_id,
                    "term": x.term,
                    "phonetic": x.phonetic,
                    "replacementText": x.replacement_text,
                }
            )
            for x in request.app.state.container.casting.pronunciations(project_id)
        ]

    @app.post(
        "/api/v1/projects/{project_id}/pronunciations",
        response_model=PronunciationEntry,
        status_code=201,
    )
    def create_pronunciation(
        project_id: str, payload: PronunciationCreate, request: Request
    ) -> PronunciationEntry:
        x = request.app.state.container.casting.create_pronunciation(
            project_id, payload.term, payload.phonetic, payload.replacement_text
        )
        return PronunciationEntry.model_validate(
            {
                "id": x.id,
                "projectId": x.project_id,
                "term": x.term,
                "phonetic": x.phonetic,
                "replacementText": x.replacement_text,
            }
        )

    @app.post("/api/v1/projects/{project_id}/voices/preview", response_model=VoicePreview)
    def preview_voice(
        project_id: str, payload: VoicePreviewRequest, request: Request
    ) -> VoicePreview:
        try:
            preview = DirectionService(request.app.state.container).preview(
                project_id, payload.text, payload.voice_profile_id, payload.direction
            )
            return preview.model_copy(update={"audio_url": artifact_url(project_id, preview.asset_path)})
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/segments/{segment_id}/generate",
        response_model=SegmentRender,
        status_code=202,
    )
    def generate_segment(
        project_id: str, segment_id: str, payload: SegmentRenderRequest, request: Request
    ) -> SegmentRender:
        return segment_render_with_url(
            project_id, SegmentRenderer(request.app.state.container).render(project_id, segment_id, payload)
        )

    @app.get(
        "/api/v1/projects/{project_id}/segments/{segment_id}/renders",
        response_model=list[SegmentRender],
    )
    def list_segment_renders(project_id: str, segment_id: str, request: Request) -> list[SegmentRender]:
        try:
            return [
                segment_render_with_url(project_id, item)
                for item in SegmentRenderer(request.app.state.container).history(project_id, segment_id)
            ]
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/segments/{segment_id}/renders/compare",
        response_model=SegmentRenderComparison,
    )
    def compare_segment_renders(
        project_id: str, segment_id: str, request: Request
    ) -> SegmentRenderComparison:
        try:
            comparison = SegmentRenderer(request.app.state.container).compare(project_id, segment_id)
            return comparison.model_copy(
                update={
                    "current_render": segment_render_with_url(project_id, comparison.current_render)
                    if comparison.current_render
                    else None,
                    "previous_render": segment_render_with_url(project_id, comparison.previous_render)
                    if comparison.previous_render
                    else None,
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/segments/{segment_id}/review-inspector",
        response_model=SegmentReviewInspector,
    )
    def get_segment_review_inspector(
        project_id: str, segment_id: str, request: Request
    ) -> SegmentReviewInspector:
        try:
            inspector = ReviewWorkbenchService(request.app.state.container).inspector(
                project_id, segment_id
            )
            return inspector.model_copy(
                update={
                    "render_history": [
                        segment_render_with_url(project_id, item)
                        for item in inspector.render_history
                    ]
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/review-timeline",
        response_model=ChapterReviewTimeline,
    )
    def get_chapter_review_timeline(
        project_id: str, chapter_id: str, request: Request
    ) -> ChapterReviewTimeline:
        try:
            timeline = ReviewWorkbenchService(request.app.state.container).chapter_timeline(
                project_id, chapter_id
            )
            return timeline.model_copy(
                update={
                    "chapter_render": chapter_render_with_url(project_id, timeline.chapter_render)
                    if timeline.chapter_render
                    else None,
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/approval",
        response_model=ChapterApproval,
    )
    def get_chapter_approval(
        project_id: str, chapter_id: str, request: Request
    ) -> ChapterApproval:
        try:
            return ReviewWorkbenchService(request.app.state.container).chapter_approval(
                project_id, chapter_id
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/approval",
        response_model=ChapterApproval,
        status_code=201,
    )
    def approve_chapter(
        project_id: str,
        chapter_id: str,
        payload: ChapterApprovalRequest,
        request: Request,
    ) -> ChapterApproval:
        try:
            return ReviewWorkbenchService(request.app.state.container).approve_chapter(
                project_id,
                chapter_id,
                payload.approved_by,
                payload.note,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/sound-assets",
        response_model=list[AmbienceAsset],
    )
    def list_sound_assets(project_id: str, request: Request) -> list[AmbienceAsset]:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return [ambience_asset_model(item) for item in container.ambience.assets(project_id)]

    @app.post(
        "/api/v1/projects/{project_id}/sound-assets/from-path",
        response_model=AmbienceAsset,
        status_code=201,
    )
    def create_sound_asset_from_path(
        project_id: str, payload: AmbienceAssetCreate, request: Request
    ) -> AmbienceAsset:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        asset_type = validate_sound_choice(
            payload.asset_type, {"ambience", "music", "sfx"}, "asset type"
        )
        asset_path = Path(payload.asset_path).expanduser()
        if not asset_path.is_file():
            raise HTTPException(status_code=422, detail="Sound asset file was not found.")
        try:
            duration_ms = payload.duration_ms if payload.duration_ms is not None else wav_duration_ms(asset_path)
        except (wave.Error, ValueError, OSError) as error:
            raise HTTPException(
                status_code=422, detail=f"Sound asset must be a readable WAV file: {error}."
            ) from error
        record = container.ambience.create_asset(
            project_id,
            payload.name.strip() or asset_path.stem,
            str(asset_path),
            payload.license_note,
            payload.provenance,
            asset_type=asset_type,
            duration_ms=duration_ms,
        )
        return ambience_asset_model(record)

    @app.post(
        "/api/v1/projects/{project_id}/sound-assets",
        response_model=AmbienceAsset,
        status_code=201,
    )
    async def upload_sound_asset(
        project_id: str,
        request: Request,
        file: UploadFile = File(...),
        asset_type: str = Form("ambience"),
        name: str | None = Form(None),
        license_note: str = Form(""),
        provenance: str = Form("local_upload"),
    ) -> AmbienceAsset:
        container: AppContainer = request.app.state.container
        project = container.projects.get(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        normalized_type = validate_sound_choice(asset_type, {"ambience", "music", "sfx"}, "asset type")
        filename = Path(file.filename or "sound.wav").name
        if Path(filename).suffix.lower() not in {".wav", ".wave"}:
            raise HTTPException(
                status_code=422,
                detail="Sound Design currently accepts WAV assets for local Python mixing.",
            )
        root = Path(project.artifact_path) / "sound-design" / "assets"
        root.mkdir(parents=True, exist_ok=True)
        asset_path = root / f"{uuid4().hex}_{filename}"
        asset_path.write_bytes(await file.read())
        try:
            duration_ms = wav_duration_ms(asset_path)
        except (wave.Error, ValueError, OSError) as error:
            asset_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=422, detail=f"Sound asset must be a readable WAV file: {error}."
            ) from error
        record = container.ambience.create_asset(
            project_id,
            (name or Path(filename).stem).strip(),
            str(asset_path),
            license_note,
            provenance,
            asset_type=normalized_type,
            duration_ms=duration_ms,
        )
        return ambience_asset_model(record)

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/sound-cues",
        response_model=list[AmbienceCue],
    )
    def list_chapter_sound_cues(
        project_id: str, chapter_id: str, request: Request
    ) -> list[AmbienceCue]:
        container: AppContainer = request.app.state.container
        chapter = container.structure.chapter(chapter_id)
        if not chapter or chapter.project_id != project_id:
            raise HTTPException(status_code=404, detail="Chapter or project not found.")
        return [ambience_cue_model(item) for item in container.ambience.cues_for_chapter(chapter_id)]

    @app.get(
        "/api/v1/scenes/{scene_id}/sound-cues",
        response_model=list[AmbienceCue],
    )
    def list_scene_sound_cues(scene_id: str, request: Request) -> list[AmbienceCue]:
        scene = request.app.state.container.structure.scene(scene_id)
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found.")
        return [ambience_cue_model(item) for item in request.app.state.container.ambience.cues_for_scene(scene_id)]

    @app.post(
        "/api/v1/projects/{project_id}/sound-cues",
        response_model=AmbienceCue,
        status_code=201,
    )
    def create_sound_cue(
        project_id: str, payload: AmbienceCueCreate, request: Request
    ) -> AmbienceCue:
        container: AppContainer = request.app.state.container
        scene = container.structure.scene(payload.scene_id)
        chapter = container.structure.chapter(scene.chapter_id) if scene else None
        if not scene or not chapter or chapter.project_id != project_id:
            raise HTTPException(status_code=404, detail="Scene or project not found.")
        cue_type = validate_sound_choice(payload.cue_type, {"ambience", "music", "sfx"}, "cue type")
        render_mode = validate_sound_choice(
            payload.render_mode, {"light", "light_cinematic", "dramatized", "all"}, "render mode"
        )
        if not payload.asset_id:
            raise HTTPException(status_code=422, detail="Sound cues require an assetId.")
        asset = container.ambience.asset(payload.asset_id)
        if not asset or asset.project_id != project_id:
            raise HTTPException(status_code=422, detail="Sound cue asset was not found in this project.")
        if payload.start_ms < 0 or payload.fade_in_ms < 0 or payload.fade_out_ms < 0:
            raise HTTPException(status_code=422, detail="Cue timing values cannot be negative.")
        if payload.gain_db > 6 or payload.gain_db < -80:
            raise HTTPException(status_code=422, detail="Cue gain must be between -80 dB and 6 dB.")
        record = container.ambience.create_cue(
            payload.scene_id,
            payload.asset_id,
            cue_type,
            payload.start_ms,
            payload.gain_db,
            payload.fade_in_ms,
            payload.fade_out_ms,
            payload.ducking,
            render_mode,
            payload.no_sfx,
        )
        return ambience_cue_model(record)

    @app.post(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/assemble",
        response_model=ChapterRender,
        status_code=202,
    )
    def assemble_chapter(
        project_id: str,
        chapter_id: str,
        request: Request,
        payload: ChapterAssemblyRequest | None = None,
    ) -> ChapterRender:
        try:
            render = ChapterAssembler(request.app.state.container).assemble(
                project_id, chapter_id, payload.render_mode if payload else "speech_only"
            )
            return chapter_render_with_url(project_id, render)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/production-status",
        response_model=ChapterProductionStatus,
    )
    def chapter_production_status(
        project_id: str, chapter_id: str, request: Request
    ) -> ChapterProductionStatus:
        try:
            production_status = ProductionService(request.app.state.container).status(project_id, chapter_id)
            return production_status.model_copy(
                update={
                    "active_render": chapter_render_with_url(project_id, production_status.active_render)
                    if production_status.active_render
                    else None
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/produce",
        response_model=Job,
        status_code=202,
    )
    def produce_chapter(
        project_id: str,
        chapter_id: str,
        request: Request,
        force: bool = False,
    ) -> Job:
        container: AppContainer = request.app.state.container
        service = ProductionService(container)
        try:
            service.status(project_id, chapter_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return container.jobs.submit_with_job(
            "chapter.produce",
            lambda job_id: service.produce(project_id, chapter_id, job_id, force),
            project_id,
            chapter_id,
        )

    @app.get(
        "/api/v1/projects/{project_id}/render-queue",
        response_model=list[RenderQueueItem],
    )
    def list_render_queue(
        project_id: str, request: Request, chapter_id: str | None = None
    ) -> list[RenderQueueItem]:
        container: AppContainer = request.app.state.container
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.render_queue.list_for_project(project_id, chapter_id)

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/renders",
        response_model=list[ChapterRender],
    )
    def list_chapter_renders(
        project_id: str, chapter_id: str, request: Request
    ) -> list[ChapterRender]:
        try:
            return [
                chapter_render_with_url(project_id, item)
                for item in ChapterAssembler(request.app.state.container).history(project_id, chapter_id)
            ]
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/chapters/{chapter_id}/active-render",
        response_model=ChapterRender,
    )
    def get_active_chapter_render(
        project_id: str, chapter_id: str, request: Request
    ) -> ChapterRender:
        try:
            return chapter_render_with_url(
                project_id, ChapterAssembler(request.app.state.container).active(project_id, chapter_id)
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/readiness/run",
        response_model=ReadinessReport,
    )
    def run_readiness_report(
        project_id: str,
        request: Request,
        payload: ReadinessRunRequest | None = None,
    ) -> ReadinessReport:
        try:
            return ReadinessService(request.app.state.container).run(
                project_id, payload.chapter_id if payload else None
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/readiness/latest",
        response_model=ReadinessReport,
    )
    def latest_readiness_report(
        project_id: str, request: Request, chapter_id: str | None = None
    ) -> ReadinessReport:
        try:
            report = ReadinessService(request.app.state.container).latest(project_id, chapter_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if not report:
            raise HTTPException(status_code=404, detail="No readiness report has been run.")
        return report

    @app.get(
        "/api/v1/projects/{project_id}/readiness/reports",
        response_model=list[ReadinessReport],
    )
    def list_readiness_reports(project_id: str, request: Request) -> list[ReadinessReport]:
        try:
            return ReadinessService(request.app.state.container).reports(project_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get(
        "/api/v1/projects/{project_id}/review-tasks",
        response_model=list[ReviewTask],
    )
    def list_review_tasks(
        project_id: str,
        request: Request,
        status_filter: str | None = None,
    ) -> list[ReviewTask]:
        try:
            return ConfidenceReviewService(request.app.state.container).list_tasks(
                project_id, status_filter
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.patch("/api/v1/review-tasks/{task_id}", response_model=ReviewTask)
    def update_review_task(
        task_id: str, payload: ReviewTaskUpdate, request: Request
    ) -> ReviewTask:
        try:
            task = ConfidenceReviewService(request.app.state.container).update_task(
                task_id, payload.status
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not task:
            raise HTTPException(status_code=404, detail="Review task not found")
        return task

    @app.get("/api/v1/projects/{project_id}/issues", response_model=list[Issue])
    def list_issues(
        project_id: str,
        request: Request,
        status_filter: str | None = None,
        segment_id: str | None = None,
    ) -> list[Issue]:
        return [
            ReviewService.issue_model(item)
            for item in request.app.state.container.review.issues(
                project_id, status_filter, segment_id
            )
        ]

    @app.post("/api/v1/projects/{project_id}/issues", response_model=Issue, status_code=201)
    def create_issue(project_id: str, payload: IssueCreate, request: Request) -> Issue:
        record = request.app.state.container.review.create_issue(
            project_id=project_id,
            chapter_id=payload.chapter_id,
            segment_id=payload.segment_id,
            category=payload.category,
            severity=payload.severity,
            title=payload.title,
            description=payload.description,
        )
        return ReviewService.issue_model(record)

    @app.patch("/api/v1/issues/{issue_id}", response_model=Issue)
    def update_issue(issue_id: str, payload: IssueUpdate, request: Request) -> Issue:
        record = request.app.state.container.review.update_issue(
            issue_id, payload.status, payload.severity
        )
        if not record:
            raise HTTPException(status_code=404, detail="Issue not found")
        return ReviewService.issue_model(record)

    @app.post(
        "/api/v1/issues/{issue_id}/apply-action",
        response_model=IssueApplyActionResponse,
    )
    def apply_issue_action(
        issue_id: str, payload: IssueApplyActionRequest, request: Request
    ) -> IssueApplyActionResponse:
        try:
            return IssueActionService(request.app.state.container).apply(issue_id, payload)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v1/issues/{issue_id}/comments", response_model=list[Comment])
    def list_comments(issue_id: str, request: Request) -> list[Comment]:
        return [
            ReviewService.comment_model(item)
            for item in request.app.state.container.review.comments(issue_id)
        ]

    @app.post("/api/v1/issues/{issue_id}/comments", response_model=Comment, status_code=201)
    def add_comment(issue_id: str, payload: CommentCreate, request: Request) -> Comment:
        return ReviewService.comment_model(
            request.app.state.container.review.add_comment(issue_id, payload.body, payload.author)
        )

    @app.post(
        "/api/v1/projects/{project_id}/segments/{segment_id}/patch",
        response_model=SegmentPatchResult,
        status_code=202,
    )
    def patch_segment(
        project_id: str, segment_id: str, payload: SegmentPatchRequest, request: Request
    ) -> SegmentPatchResult:
        try:
            return ReviewService(request.app.state.container).patch_segment(
                project_id, segment_id, payload
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/exports", response_model=ExportPackage, status_code=202
    )
    def create_export(project_id: str, payload: ExportRequest, request: Request) -> ExportPackage:
        try:
            package = ExportService(request.app.state.container).export(project_id, payload)
            return package.model_copy(
                update={"download_url": f"/api/v1/projects/{project_id}/exports/{package.id}/download"}
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/api/v1/projects/{project_id}/exports/estimate", response_model=ExportEstimate
    )
    def estimate_export(
        project_id: str, payload: ExportRequest, request: Request
    ) -> ExportEstimate:
        try:
            return ExportService(request.app.state.container).estimate(project_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/v1/projects/{project_id}/exports", response_model=list[ExportPackage])
    def list_exports(project_id: str, request: Request) -> list[ExportPackage]:
        return [
            item.model_copy(
                update={"download_url": f"/api/v1/projects/{project_id}/exports/{item.id}/download"}
            )
            for item in ExportService(request.app.state.container).list_packages(project_id)
        ]

    @app.get("/api/v1/projects/{project_id}/exports/{export_id}", response_model=ExportPackage)
    def get_export(project_id: str, export_id: str, request: Request) -> ExportPackage:
        package = ExportService(request.app.state.container).get(project_id, export_id)
        if not package:
            raise HTTPException(status_code=404, detail="Export not found")
        return package.model_copy(
            update={"download_url": f"/api/v1/projects/{project_id}/exports/{export_id}/download"}
        )

    @app.get("/api/v1/projects/{project_id}/exports/{export_id}/download")
    def download_export(project_id: str, export_id: str, request: Request) -> FileResponse:
        package = ExportService(request.app.state.container).get(project_id, export_id)
        if not package or not package.archive_path or not Path(package.archive_path).is_file():
            raise HTTPException(status_code=404, detail="Export archive not found")
        return FileResponse(package.archive_path, filename=Path(package.archive_path).name)

    return app


def _event_cursor(header_value: str | None, fallback: int) -> int:
    if not header_value:
        return fallback
    try:
        return max(0, int(header_value))
    except ValueError:
        return fallback


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)
