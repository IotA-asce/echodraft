from pathlib import Path

import pytest

from echodraft_domain import JobState


def create_payload() -> dict[str, str]:
    return {"title": "The Glass Orchard", "author": "A. Writer", "rightsStatus": "declared"}


def test_project_creation_persists_and_creates_artifact_layout(client) -> None:
    response = client.post("/api/v1/projects", json=create_payload())
    assert response.status_code == 201
    project = response.json()
    assert project["title"] == "The Glass Orchard"
    artifact_root = Path(project["artifactPath"])
    assert {item.name for item in artifact_root.iterdir()} == {
        "source", "structure", "audio", "exports", "logs", "manifests"
    }
    projects = client.get("/api/v1/projects")
    assert [item["id"] for item in projects.json()] == [project["id"]]


def test_project_creation_requires_declared_rights(client) -> None:
    response = client.post(
        "/api/v1/projects", json={"title": "Uncleared", "rightsStatus": "not_declared"}
    )
    assert response.status_code == 422


def test_job_transitions_are_durable(app, client) -> None:
    runner = app.state.container.jobs
    job = runner.enqueue("foundation.check")
    assert runner.run_inline(job.id, lambda: None).status is JobState.SUCCEEDED
    response = client.get(f"/api/v1/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_job_rejects_invalid_transition(app) -> None:
    job = app.state.container.jobs.enqueue("foundation.check")
    app.state.container.jobs_repository.transition(job.id, JobState.CANCELLED)
    with pytest.raises(ValueError):
        app.state.container.jobs_repository.transition(job.id, JobState.RUNNING)


def test_health_is_local_first(client) -> None:
    assert client.get("/health").json() == {"status": "ok", "mode": "local-first"}
