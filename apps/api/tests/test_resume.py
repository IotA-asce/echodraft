"""Checkpoint/resume behaviour for interrupted orchestrator jobs."""

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import echodraft_api.local_llm as local_llm
import echodraft_api.resume as resume_module
from echodraft_api.config import AppSettings
from echodraft_api.local_llm import CheckpointContext, LocalLlmService, OllamaGenerateResult
from echodraft_api.main import create_app
from echodraft_db.models import InferenceCacheRecord, JobCheckpointRecord
from echodraft_domain import Job, JobState, LlmExtractionRequest

RESUME_UNITS = ("alpha", "beta", "gamma", "delta")


class CountingProvider:
    """Fake Ollama provider that returns a schema-valid result and counts model calls."""

    calls = 0

    def __init__(self, _base_url: str) -> None:
        pass

    def tags(self) -> list[dict[str, object]]:
        return [{"name": "qwen3:4b"}, {"name": "qwen3-embedding"}]

    def infer(
        self,
        model: str,
        prompt: str,
        schema: dict[str, object],
        *,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> OllamaGenerateResult:
        type(self).calls += 1
        return OllamaGenerateResult(
            response={"characters": [], "warnings": []}, raw={"response": "{}"}
        )

    def generate_json(
        self, model: str, prompt: str, schema: dict[str, object]
    ) -> OllamaGenerateResult:
        return self.infer(model, prompt, schema)

    def embed(self, _request: object) -> object:
        from echodraft_domain import EmbeddingResult

        return EmbeddingResult(model="qwen3-embedding", embeddings=[[0.1, 0.2]])


def _probe_units(container: object, job: Job) -> None:
    """Resume callable: run one checkpointed extraction per probe unit."""
    llm = LocalLlmService(container)  # type: ignore[arg-type]
    for unit in RESUME_UNITS:
        request = LlmExtractionRequest(
            model="qwen3:4b", task="resume_probe", prompt=f"probe unit {unit}"
        )
        llm.extract(
            job.project_id,
            request,
            job.id,
            checkpoint=CheckpointContext(
                job_id=job.id,
                project_id=job.project_id,
                stage="resume.probe",
                scope={"unit": unit},
            ),
        )


def _wait_for_status(container: object, job_id: str, status: JobState) -> Job:
    for _ in range(200):
        job = container.jobs_repository.get(job_id)  # type: ignore[attr-defined]
        if job and job.status == status:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {status}")


def _project_with_source(settings: AppSettings) -> str:
    app = create_app(settings)
    with TestClient(app) as client:
        project = client.post(
            "/api/v1/projects", json={"title": "Resume", "rightsStatus": "declared"}
        ).json()["id"]
        imported = client.post(
            f"/api/v1/projects/{project}/source/import",
            files={"file": ("book.txt", b"Chapter 1\n\nMara said hello.", "text/plain")},
            data={"rightsAcknowledged": "true"},
        ).json()
        for _ in range(100):
            job = client.get(f"/api/v1/jobs/{imported['id']}").json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "succeeded"
    return project


def test_resume_reruns_only_uncheckpointed_units(
    settings: AppSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_llm, "OllamaProvider", CountingProvider)
    monkeypatch.setitem(resume_module.RESUME_REGISTRY, "resume.probe", _probe_units)
    CountingProvider.calls = 0

    project = _project_with_source(settings)

    # Phase 1: a first (partial) run that checkpoints and caches every probe unit, left
    # behind as an interrupted RUNNING job.
    cold_app = create_app(settings)
    with TestClient(cold_app) as _cold_client:
        cold_container = cold_app.state.container
        job = cold_container.jobs_repository.create("resume.probe", project_id=project)
        _probe_units(cold_container, job)
        cold_calls = CountingProvider.calls
        assert cold_calls == len(RESUME_UNITS)

        checkpoints = cold_container.orchestrator_repository.checkpoints_for_job(job.id)
        assert len(checkpoints) == len(RESUME_UNITS)

        # Drop the checkpoint + cache for two units, simulating work that never finished
        # before the interruption; the surviving checkpoints keep the job resumable.
        dropped = [cp for cp in checkpoints if cp.scope_json and '"delta"' in cp.scope_json]
        dropped += [cp for cp in checkpoints if cp.scope_json and '"gamma"' in cp.scope_json]
        with cold_container.jobs_repository.database.session() as session:
            for cp in dropped:
                if cp.output_ref:
                    session.execute(
                        delete(InferenceCacheRecord).where(
                            InferenceCacheRecord.cache_key == cp.output_ref
                        )
                    )
                session.execute(
                    delete(JobCheckpointRecord).where(
                        JobCheckpointRecord.unit_key == cp.unit_key
                    )
                )
            session.commit()
        # Force the job back to RUNNING to model an interrupted, in-flight job.
        with cold_container.jobs_repository.database.session() as session:
            from echodraft_db.models import JobRecord

            job_record = session.get(JobRecord, job.id)
            assert job_record is not None
            job_record.status = JobState.RUNNING.value
            session.commit()

    # Phase 2: restart. A brand-new container reconciles the interrupted job, re-queues it
    # for resume, and re-runs it. Only the two un-checkpointed units should hit the model.
    CountingProvider.calls = 0
    warm_app = create_app(settings)
    with TestClient(warm_app) as _warm_client:
        warm_container = warm_app.state.container
        # The job was re-queued and re-run purely from its persisted state (a failed job
        # would never have executed), and only the two un-checkpointed units hit the model.
        _wait_for_status(warm_container, job.id, JobState.SUCCEEDED)
        assert CountingProvider.calls == 2
        assert CountingProvider.calls < cold_calls
        # Every unit is checkpointed done again after the resume completes.
        final = warm_container.orchestrator_repository.checkpoints_for_job(job.id)
        assert {cp.status for cp in final} == {"done"}
        assert len(final) == len(RESUME_UNITS)


def test_reconcile_resumes_checkpointed_registered_jobs_only(client) -> None:
    container = client.app.state.container
    project = client.post(
        "/api/v1/projects", json={"title": "Reconcile", "rightsStatus": "declared"}
    ).json()["id"]

    resumable = container.jobs_repository.create("structure.extract", project_id=project)
    no_checkpoints = container.jobs_repository.create("structure.extract", project_id=project)
    unregistered = container.jobs_repository.create("cast.discovery", project_id=project)
    for job in (resumable, no_checkpoints, unregistered):
        container.jobs_repository.transition(job.id, JobState.RUNNING)

    # Only the first job recorded orchestrator checkpoints.
    container.orchestrator_repository.upsert_checkpoint(
        unit_key=f"unit_{resumable.id}",
        job_id=resumable.id,
        project_id=project,
        stage="structure.extract.refine",
        stage_version="1",
        scope={"sceneId": "scene_1"},
        status="done",
    )

    from echodraft_api.resume import RESUME_REGISTRY

    resumed = container.jobs_repository.reconcile_interrupted(
        resumable_job_types=set(RESUME_REGISTRY),
        has_checkpoints=lambda job_id: bool(
            container.orchestrator_repository.checkpoints_for_job(job_id)
        ),
    )

    assert [job.id for job in resumed] == [resumable.id]
    assert container.jobs_repository.get(resumable.id).status == JobState.QUEUED
    assert "resumedAt" in container.jobs_repository.get(resumable.id).progress
    assert container.jobs_repository.get(no_checkpoints.id).status == JobState.FAILED
    assert container.jobs_repository.get(unregistered.id).status == JobState.FAILED
