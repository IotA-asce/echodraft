from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from echodraft_db import (
    AmbienceRepository,
    CastGraphRepository,
    CastingRepository,
    CastMergeDecisionRepository,
    Database,
    JobRepository,
    LlmRunRepository,
    LocalAiRepository,
    OrchestratorRepository,
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
from .orchestrator import HardwareProbe, OrchestratorPools, tts_device
from .resume import RESUME_REGISTRY
from .tts_settings import TtsSettingsStore
from .tts_worker import TtsWorkerManager

if TYPE_CHECKING:
    from .tts_providers import TtsProvider


@dataclass
class AppContainer:
    settings: AppSettings
    artifacts: ArtifactStore
    projects: ProjectRepository
    jobs_repository: JobRepository
    orchestrator_repository: OrchestratorRepository
    sources: SourceDocumentRepository
    source_artifacts: SourceArtifactRepository
    structure: StructureRepository
    casting: CastingRepository
    cast_graph: CastGraphRepository
    cast_merge_decisions: CastMergeDecisionRepository
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
    tts_worker_manager: TtsWorkerManager
    orchestrator_pools: OrchestratorPools
    jobs: InProcessJobRunner


def build_container(settings: AppSettings) -> AppContainer:
    database = Database(settings.database_url)
    database.create_schema()
    artifacts = ArtifactStore(settings.artifact_root)
    jobs_repository = JobRepository(database)
    orchestrator_repository = OrchestratorRepository(database)
    # Jobs interrupted mid-run cannot continue in place. Resumable, checkpointed jobs
    # are re-queued (and re-run below once the runner exists); everything else fails closed.
    resumed_jobs = jobs_repository.reconcile_interrupted(
        resumable_job_types=set(RESUME_REGISTRY),
        has_checkpoints=lambda job_id: bool(
            orchestrator_repository.checkpoints_for_job(job_id)
        ),
    )
    tts_settings = TtsSettingsStore(settings)
    orchestrator_pools = OrchestratorPools.from_probe(
        HardwareProbe(),
        llm_workers_override=settings.llm_worker_override,
        subprocess_workers_override=settings.subprocess_worker_override,
        tts_workers_override=settings.tts_worker_override,
        audiogen_workers_override=settings.audiogen_worker_override,
        model_vram_budget_gib=settings.model_vram_budget_gib,
    )
    tts_worker_manager = TtsWorkerManager(
        execution_pool=orchestrator_pools.tts,
        device=tts_device(orchestrator_pools.hardware),
    )
    adapter = tts_settings.adapter(worker_manager=tts_worker_manager)
    container = AppContainer(
        settings=settings,
        artifacts=artifacts,
        projects=ProjectRepository(database, str(settings.artifact_root)),
        jobs_repository=jobs_repository,
        orchestrator_repository=orchestrator_repository,
        sources=SourceDocumentRepository(database),
        source_artifacts=SourceArtifactRepository(database),
        structure=StructureRepository(database),
        casting=CastingRepository(database),
        cast_graph=CastGraphRepository(database),
        cast_merge_decisions=CastMergeDecisionRepository(database),
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
        tts_worker_manager=tts_worker_manager,
        orchestrator_pools=orchestrator_pools,
        jobs=InProcessJobRunner(jobs_repository, settings.max_concurrent_jobs),
    )
    # Re-run interrupted, checkpointed jobs now that the runner is available. Their
    # extraction stages skip already-checkpointed units via the inference cache.
    for job in resumed_jobs:
        resume_callable = RESUME_REGISTRY.get(job.job_type)
        if resume_callable is None:
            continue
        container.jobs.resume(job.id, partial(resume_callable, container, job))
    return container
