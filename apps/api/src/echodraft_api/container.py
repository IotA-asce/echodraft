from dataclasses import dataclass

from echodraft_db import Database, JobRepository, ProjectRepository, SourceDocumentRepository, StructureRepository

from .artifacts import ArtifactStore
from .config import AppSettings
from .jobs import InProcessJobRunner


@dataclass
class AppContainer:
    settings: AppSettings
    artifacts: ArtifactStore
    projects: ProjectRepository
    jobs_repository: JobRepository
    sources: SourceDocumentRepository
    structure: StructureRepository
    jobs: InProcessJobRunner


def build_container(settings: AppSettings) -> AppContainer:
    database = Database(settings.database_url)
    database.create_schema()
    artifacts = ArtifactStore(settings.artifact_root)
    jobs_repository = JobRepository(database)
    return AppContainer(
        settings=settings,
        artifacts=artifacts,
        projects=ProjectRepository(database, str(settings.artifact_root)),
        jobs_repository=jobs_repository,
        sources=SourceDocumentRepository(database),
        structure=StructureRepository(database),
        jobs=InProcessJobRunner(jobs_repository),
    )
