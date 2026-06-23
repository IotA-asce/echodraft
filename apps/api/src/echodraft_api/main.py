from collections.abc import Awaitable, Callable
from uuid import uuid4

from echodraft_domain import Job, Project, ProjectCreate
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .config import AppSettings
from .container import AppContainer, build_container
from .logging import configure_logging

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

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)
