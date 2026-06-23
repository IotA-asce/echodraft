from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from echodraft_domain import AssignVoice, Chapter, Character, CharacterCreate, Job, Project, ProjectCreate, PronunciationCreate, PronunciationEntry, ReparseRequest, Scene, Segment, SegmentRender, SegmentRenderRequest, SegmentRevision, SegmentUpdate, SourceDocument, StructureRequest, VoicePreview, VoicePreviewRequest, VoiceProfile, VoiceProfileCreate
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .config import AppSettings
from .container import AppContainer, build_container
from .logging import configure_logging
from .ingestion import IngestionError, IngestionService, PARSER_VERSION
from .structure import StructureService, chapter_model, revision_model, scene_model, segment_model
from .direction import DirectionService
from .rendering import SegmentRenderer

logger = configure_logging()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_environment()
    container = build_container(resolved_settings)
    app = FastAPI(title="echodraft API", version="0.1.0")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    async def import_source(project_id: str, request: Request, file: UploadFile = File(...), rights_acknowledged: bool = Form(..., alias="rightsAcknowledged"), parser_version: str = Form(PARSER_VERSION, alias="parserVersion")) -> Job:
        if not rights_acknowledged:
            raise HTTPException(status_code=422, detail="Rights acknowledgement is required for import.")
        container: AppContainer = request.app.state.container
        service = IngestionService(container)
        try:
            source_id = service.stage(project_id, file.filename or "manuscript.txt", file.content_type, await file.read(), parser_version)
        except KeyError:
            raise HTTPException(status_code=404, detail="Project not found") from None
        except IngestionError as error:
            raise HTTPException(status_code=415, detail=str(error)) from error
        source = container.sources.latest(project_id)
        assert source
        job = container.jobs.submit("source.import", lambda: service.process(source_id, project_id, source.original_filename, source.mime_type, parser_version, Path(source.original_path)), project_id)
        return job

    @app.post("/api/v1/projects/{project_id}/source/reparse", response_model=Job, status_code=202)
    def reparse_source(project_id: str, payload: ReparseRequest, request: Request) -> Job:
        container: AppContainer = request.app.state.container
        previous = container.sources.latest(project_id)
        if not previous:
            raise HTTPException(status_code=404, detail="No source document found")
        service = IngestionService(container)
        try:
            source_id = service.stage(project_id, previous.original_filename, previous.mime_type, Path(previous.original_path).read_bytes(), payload.parser_version)
        except IngestionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        source = container.sources.latest(project_id)
        assert source
        return container.jobs.submit("source.reparse", lambda: service.process(source_id, project_id, source.original_filename, source.mime_type, payload.parser_version, Path(source.original_path)), project_id)

    @app.get("/api/v1/projects/{project_id}/source", response_model=SourceDocument)
    def get_source(project_id: str, request: Request) -> SourceDocument:
        container: AppContainer = request.app.state.container
        source = container.sources.latest(project_id)
        if not source:
            raise HTTPException(status_code=404, detail="No source document found")
        if source.canonical_path and Path(source.canonical_path).exists():
            source.preview = Path(source.canonical_path).read_text(encoding="utf-8")[:6000]
        return source

    @app.post("/api/v1/projects/{project_id}/structure/extract", response_model=Job, status_code=202)
    def extract_structure(project_id: str, payload: StructureRequest, request: Request) -> Job:
        container: AppContainer = request.app.state.container
        service = StructureService(container)
        if not container.projects.get(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        return container.jobs.submit("structure.extract", lambda: service.extract(project_id, payload.max_segment_chars), project_id)

    @app.get("/api/v1/projects/{project_id}/chapters", response_model=list[Chapter])
    def list_chapters(project_id: str, request: Request) -> list[Chapter]:
        return [chapter_model(item) for item in request.app.state.container.structure.chapters(project_id)]

    @app.get("/api/v1/chapters/{chapter_id}", response_model=Chapter)
    def get_chapter(chapter_id: str, request: Request) -> Chapter:
        record = request.app.state.container.structure.chapter(chapter_id)
        if not record:
            raise HTTPException(status_code=404, detail="Chapter not found")
        return chapter_model(record)

    @app.get("/api/v1/chapters/{chapter_id}/scenes", response_model=list[Scene])
    def list_scenes(chapter_id: str, request: Request) -> list[Scene]:
        return [scene_model(item) for item in request.app.state.container.structure.scenes(chapter_id)]

    @app.get("/api/v1/scenes/{scene_id}/segments", response_model=list[Segment])
    def list_segments(scene_id: str, request: Request) -> list[Segment]:
        return [segment_model(item) for item in request.app.state.container.structure.segments(scene_id)]

    @app.patch("/api/v1/segments/{segment_id}", response_model=Segment)
    def update_segment(segment_id: str, payload: SegmentUpdate, request: Request) -> Segment:
        record = request.app.state.container.structure.update_segment(segment_id, payload.text_content)
        if not record:
            raise HTTPException(status_code=404, detail="Segment not found")
        return segment_model(record)

    @app.get("/api/v1/segments/{segment_id}/revisions", response_model=list[SegmentRevision])
    def list_segment_revisions(segment_id: str, request: Request) -> list[SegmentRevision]:
        return [revision_model(item) for item in request.app.state.container.structure.revisions(segment_id)]

    @app.get("/api/v1/projects/{project_id}/characters", response_model=list[Character])
    def list_characters(project_id: str, request: Request) -> list[Character]:
        return [Character.model_validate({"id": x.id, "projectId": x.project_id, "displayName": x.display_name, "aliases": __import__("json").loads(x.aliases_json), "roleType": x.role_type, "confidence": x.confidence, "notes": x.notes}) for x in request.app.state.container.casting.characters(project_id)]

    @app.post("/api/v1/projects/{project_id}/characters", response_model=Character, status_code=201)
    def create_character(project_id: str, payload: CharacterCreate, request: Request) -> Character:
        x = request.app.state.container.casting.create_character(project_id, payload.display_name, payload.aliases, payload.role_type, payload.confidence, payload.notes)
        return Character.model_validate({"id": x.id, "projectId": x.project_id, "displayName": x.display_name, "aliases": payload.aliases, "roleType": x.role_type, "confidence": x.confidence, "notes": x.notes})

    @app.get("/api/v1/projects/{project_id}/voices", response_model=list[VoiceProfile])
    def list_voices(project_id: str, request: Request) -> list[VoiceProfile]:
        return [VoiceProfile.model_validate({"id": x.id, "projectId": x.project_id, "name": x.name, "backend": x.backend, "stylePrompt": x.style_prompt}) for x in request.app.state.container.casting.voices(project_id)]

    @app.post("/api/v1/projects/{project_id}/voices", response_model=VoiceProfile, status_code=201)
    def create_voice(project_id: str, payload: VoiceProfileCreate, request: Request) -> VoiceProfile:
        x = request.app.state.container.casting.create_voice(project_id, payload.name, payload.backend, payload.style_prompt)
        return VoiceProfile.model_validate({"id": x.id, "projectId": x.project_id, "name": x.name, "backend": x.backend, "stylePrompt": x.style_prompt})

    @app.post("/api/v1/characters/{character_id}/assign-voice", status_code=200)
    def assign_voice(character_id: str, payload: AssignVoice, request: Request) -> dict[str, str]:
        request.app.state.container.casting.assign(character_id, payload.voice_profile_id)
        return {"status": "assigned"}

    @app.get("/api/v1/projects/{project_id}/pronunciations", response_model=list[PronunciationEntry])
    def list_pronunciations(project_id: str, request: Request) -> list[PronunciationEntry]:
        return [PronunciationEntry.model_validate({"id": x.id, "projectId": x.project_id, "term": x.term, "phonetic": x.phonetic, "replacementText": x.replacement_text}) for x in request.app.state.container.casting.pronunciations(project_id)]

    @app.post("/api/v1/projects/{project_id}/pronunciations", response_model=PronunciationEntry, status_code=201)
    def create_pronunciation(project_id: str, payload: PronunciationCreate, request: Request) -> PronunciationEntry:
        x = request.app.state.container.casting.create_pronunciation(project_id, payload.term, payload.phonetic, payload.replacement_text)
        return PronunciationEntry.model_validate({"id": x.id, "projectId": x.project_id, "term": x.term, "phonetic": x.phonetic, "replacementText": x.replacement_text})

    @app.post("/api/v1/projects/{project_id}/voices/preview", response_model=VoicePreview)
    def preview_voice(project_id: str, payload: VoicePreviewRequest, request: Request) -> VoicePreview:
        try:
            return DirectionService(request.app.state.container).preview(project_id, payload.text, payload.voice_profile_id, payload.direction)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/v1/projects/{project_id}/segments/{segment_id}/generate", response_model=SegmentRender, status_code=202)
    def generate_segment(project_id: str, segment_id: str, payload: SegmentRenderRequest, request: Request) -> SegmentRender:
        return SegmentRenderer(request.app.state.container).render(project_id, segment_id, payload)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)
