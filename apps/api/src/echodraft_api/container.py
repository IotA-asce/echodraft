from dataclasses import dataclass

from echodraft_db import (
    CastingRepository,
    Database,
    JobRepository,
    ProjectRepository,
    ReviewRepository,
    SourceDocumentRepository,
    StructureRepository,
)

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
    casting: CastingRepository
    review: ReviewRepository
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
        casting=CastingRepository(database),
        review=ReviewRepository(database),
        jobs=InProcessJobRunner(jobs_repository),
    )
