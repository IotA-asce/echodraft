from dataclasses import dataclass
from typing import TYPE_CHECKING

from echodraft_db import (
    AmbienceRepository,
    CastingRepository,
    Database,
    JobRepository,
    LocalAiRepository,
    ProjectRepository,
    ProductionSettingsRepository,
    ReviewRepository,
    SourceDocumentRepository,
    StructureRepository,
)

from .artifacts import ArtifactStore
from .config import AppSettings
from .jobs import InProcessJobRunner
from .tts_settings import TtsSettingsStore

if TYPE_CHECKING:
    from .direction import TtsAdapter


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
    ambience: AmbienceRepository
    production: ProductionSettingsRepository
    local_ai: LocalAiRepository
    tts_settings: TtsSettingsStore
    tts_adapter: "TtsAdapter"
    jobs: InProcessJobRunner


def build_container(settings: AppSettings) -> AppContainer:
    database = Database(settings.database_url)
    database.create_schema()
    artifacts = ArtifactStore(settings.artifact_root)
    jobs_repository = JobRepository(database)
    jobs_repository.reconcile_interrupted()
    tts_settings = TtsSettingsStore(settings)
    adapter = tts_settings.adapter()
    return AppContainer(
        settings=settings,
        artifacts=artifacts,
        projects=ProjectRepository(database, str(settings.artifact_root)),
        jobs_repository=jobs_repository,
        sources=SourceDocumentRepository(database),
        structure=StructureRepository(database),
        casting=CastingRepository(database),
        review=ReviewRepository(database),
        ambience=AmbienceRepository(database),
        production=ProductionSettingsRepository(database),
        local_ai=LocalAiRepository(database),
        tts_settings=tts_settings,
        tts_adapter=adapter,
        jobs=InProcessJobRunner(jobs_repository),
    )
