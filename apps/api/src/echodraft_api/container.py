from dataclasses import dataclass
from typing import TYPE_CHECKING

from echodraft_db import (
    AmbienceRepository,
    CastingRepository,
    Database,
    JobRepository,
    LlmRunRepository,
    LocalAiRepository,
    ProjectRepository,
    ProductionSettingsRepository,
    RenderQueueRepository,
    ReviewRepository,
    SegmentDirectionRepository,
    SpeakerAttributionRepository,
    SourceArtifactRepository,
    SourceDocumentRepository,
    StructureRepository,
)

from .artifacts import ArtifactStore
from .config import AppSettings
from .jobs import InProcessJobRunner
from .tts_settings import TtsSettingsStore

if TYPE_CHECKING:
    from .tts_providers import TtsProvider


@dataclass
class AppContainer:
    settings: AppSettings
    artifacts: ArtifactStore
    projects: ProjectRepository
    jobs_repository: JobRepository
    sources: SourceDocumentRepository
    source_artifacts: SourceArtifactRepository
    structure: StructureRepository
    casting: CastingRepository
    review: ReviewRepository
    speaker_attributions: SpeakerAttributionRepository
    ambience: AmbienceRepository
    production: ProductionSettingsRepository
    render_queue: RenderQueueRepository
    segment_directions: SegmentDirectionRepository
    local_ai: LocalAiRepository
    llm_runs: LlmRunRepository
    tts_settings: TtsSettingsStore
    tts_adapter: "TtsProvider"
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
        source_artifacts=SourceArtifactRepository(database),
        structure=StructureRepository(database),
        casting=CastingRepository(database),
        review=ReviewRepository(database),
        speaker_attributions=SpeakerAttributionRepository(database),
        ambience=AmbienceRepository(database),
        production=ProductionSettingsRepository(database),
        render_queue=RenderQueueRepository(database),
        segment_directions=SegmentDirectionRepository(database),
        local_ai=LocalAiRepository(database),
        llm_runs=LlmRunRepository(database),
        tts_settings=tts_settings,
        tts_adapter=adapter,
        jobs=InProcessJobRunner(jobs_repository),
    )
