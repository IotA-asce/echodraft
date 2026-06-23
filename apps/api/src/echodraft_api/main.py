from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from echodraft_domain import Job, Project, ProjectCreate, ReparseRequest, SourceDocument
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from .config import AppSettings
from .container import AppContainer, build_container
from .logging import configure_logging
from .ingestion import IngestionError, IngestionService, PARSER_VERSION

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

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)
