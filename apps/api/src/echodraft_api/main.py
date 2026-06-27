from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from echodraft_domain import (
    AssignVoice,
    Chapter,
    ChapterAssemblyRequest,
    ChapterRender,
    Character,
    CharacterCreate,
    Comment,
    CommentCreate,
    ExportPackage,
    ExportRequest,
    Issue,
    IssueCreate,
    IssueUpdate,
    Job,
    Project,
    ProjectCreate,
    PronunciationCreate,
    PronunciationEntry,
    ReparseRequest,
    Scene,
    Segment,
    SegmentPatchRequest,
    SegmentPatchResult,
    SegmentRender,
    SegmentRenderRequest,
    SegmentRevision,
    SegmentUpdate,
    SourceDocument,
    StructureRequest,
    VoicePreview,
    VoicePreviewRequest,
    VoiceProfile,
    VoiceProfileCreate,
    VoiceProfileUpdate,
    KokoroSetupInstallRequest,
    KokoroSetupStatus,
    LocalAiHealth,
    LocalAiInstallation,
    LocalAiInstallJob,
    LocalAiInstallRequest,
    LocalAiModelCatalogItem,
    TtsSettings,
    TtsSettingsUpdate,
    TtsTestRequest,
    ProjectProductionSettings,
    ProjectProductionSettingsUpdate,
    SegmentProductionOverride,
    SegmentProductionOverrideUpdate,
    ChapterProductionStatus,
)
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import AppSettings
from .container import AppContainer, build_container
from .logging import configure_logging
from .ingestion import IngestionError, IngestionService, PARSER_VERSION
from .structure import StructureService, chapter_model, revision_model, scene_model, segment_model
from .direction import DirectionService
from .rendering import SegmentRenderer
from .assembly import ChapterAssembler
from .review import ReviewService
from .exporting import ExportService
from .production import ProductionService
from .kokoro_setup import ManagedKokoroSetupService
from .local_ai import LocalAiService

logger = configure_logging()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_environment()
    container = build_container(resolved_settings)
    app = FastAPI(title="echodraft API", version="0.1.0")
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

    @app.put("/api/v1/settings/tts", response_model=TtsSettings)
    def save_tts_settings(payload: TtsSettingsUpdate, request: Request) -> TtsSettings:
        container: AppContainer = request.app.state.container
        try:
            saved = container.tts_settings.save(payload)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        container.tts_adapter = container.tts_settings.adapter()
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
            container.tts_adapter = container.tts_settings.adapter()

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
        job = container.jobs.submit(
            "source.import",
            lambda: service.process(
                source_id,
                project_id,
                source.original_filename,
                source.mime_type,
                parser_version,
                Path(source.original_path),
            ),
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

    @app.post(
        "/api/v1/projects/{project_id}/structure/extract", response_model=Job, status_code=202
    )
    def extract_structure(project_id: str, payload: StructureRequest, request: Request) -> Job:
        container: AppContainer = request.app.state.container
        service = StructureService(container)
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.jobs.submit(
            "structure.extract",
            lambda: service.extract(project_id, payload.max_segment_chars),
            project_id,
        )

    @app.get("/api/v1/projects/{project_id}/chapters", response_model=list[Chapter])
    def list_chapters(project_id: str, request: Request) -> list[Chapter]:
        return [
            chapter_model(item)
            for item in request.app.state.container.structure.chapters(project_id)
        ]

    @app.get("/api/v1/chapters/{chapter_id}", response_model=Chapter)
    def get_chapter(chapter_id: str, request: Request) -> Chapter:
        record = request.app.state.container.structure.chapter(chapter_id)
        if not record:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return chapter_model(record)

    @app.get("/api/v1/chapters/{chapter_id}/scenes", response_model=list[Scene])
    def list_scenes(chapter_id: str, request: Request) -> list[Scene]:
        return [
            scene_model(item) for item in request.app.state.container.structure.scenes(chapter_id)
        ]

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
                project_id, payload.narrator_voice_profile_id, payload.default_direction
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

    @app.get("/api/v1/projects/{project_id}/characters", response_model=list[Character])
    def list_characters(project_id: str, request: Request) -> list[Character]:
        return [
            Character.model_validate(
                {
                    "id": x.id,
                    "projectId": x.project_id,
                    "displayName": x.display_name,
                    "aliases": __import__("json").loads(x.aliases_json),
                    "roleType": x.role_type,
                    "confidence": x.confidence,
                    "notes": x.notes,
                }
            )
            for x in request.app.state.container.casting.characters(project_id)
        ]

    @app.post("/api/v1/projects/{project_id}/characters", response_model=Character, status_code=201)
    def create_character(project_id: str, payload: CharacterCreate, request: Request) -> Character:
        x = request.app.state.container.casting.create_character(
            project_id,
            payload.display_name,
            payload.aliases,
            payload.role_type,
            payload.confidence,
            payload.notes,
        )
        return Character.model_validate(
            {
                "id": x.id,
                "projectId": x.project_id,
                "displayName": x.display_name,
                "aliases": payload.aliases,
                "roleType": x.role_type,
                "confidence": x.confidence,
                "notes": x.notes,
            }
        )

    @app.get("/api/v1/projects/{project_id}/voices", response_model=list[VoiceProfile])
    def list_voices(project_id: str, request: Request) -> list[VoiceProfile]:
        return [
            VoiceProfile.model_validate(
                {
                    "id": x.id,
                    "projectId": x.project_id,
                    "name": x.name,
                    "backend": x.backend,
                    "providerVoiceId": x.provider_voice_id,
                    "stylePrompt": x.style_prompt,
                }
            )
            for x in request.app.state.container.casting.voices(project_id)
        ]

    @app.post("/api/v1/projects/{project_id}/voices", response_model=VoiceProfile, status_code=201)
    def create_voice(
        project_id: str, payload: VoiceProfileCreate, request: Request
    ) -> VoiceProfile:
        x = request.app.state.container.casting.create_voice(
            project_id, payload.name, payload.backend, payload.provider_voice_id, payload.style_prompt
        )
        return VoiceProfile.model_validate(
            {
                "id": x.id,
                "projectId": x.project_id,
                "name": x.name,
                "backend": x.backend,
                "providerVoiceId": x.provider_voice_id,
                "stylePrompt": x.style_prompt,
            }
        )

    @app.patch("/api/v1/voices/{voice_id}", response_model=VoiceProfile)
    def update_voice(voice_id: str, payload: VoiceProfileUpdate, request: Request) -> VoiceProfile:
        x = request.app.state.container.casting.update_voice(
            voice_id, payload.name, payload.provider_voice_id, payload.style_prompt
        )
        if not x:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        return VoiceProfile.model_validate(
            {
                "id": x.id,
                "projectId": x.project_id,
                "name": x.name,
                "backend": x.backend,
                "providerVoiceId": x.provider_voice_id,
                "stylePrompt": x.style_prompt,
            }
        )

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
        request.app.state.container.casting.assign(character_id, payload.voice_profile_id)
        return {"status": "assigned"}

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

    @app.get("/api/v1/projects/{project_id}/exports", response_model=list[ExportPackage])
    def list_exports(project_id: str, request: Request) -> list[ExportPackage]:
        return [
            item.model_copy(
                update={"download_url": f"/api/v1/projects/{project_id}/exports/{item.id}/download"}
            )
            for item in ExportService(request.app.state.container).list(project_id)
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


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)
