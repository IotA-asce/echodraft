from pathlib import Path
import sqlite3

import pytest

from echodraft_db import Database
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


def test_startup_repairs_legacy_sqlite_production_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE projects (
                id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                author VARCHAR(200),
                description TEXT,
                rights_status VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                artifact_path TEXT NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE TABLE voice_profiles (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64),
                name VARCHAR(200) NOT NULL,
                backend VARCHAR(100) NOT NULL,
                style_prompt TEXT
            );
            CREATE TABLE export_packages (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64),
                format VARCHAR(16) NOT NULL,
                status VARCHAR(32) NOT NULL,
                output_path TEXT NOT NULL,
                manifest_path TEXT NOT NULL
            );
            CREATE TABLE chapter_renders (
                id VARCHAR(64) PRIMARY KEY,
                chapter_id VARCHAR(64),
                status VARCHAR(32),
                speech_path TEXT,
                manifest_path TEXT,
                duration_ms INTEGER
            );
            INSERT INTO voice_profiles (id, project_id, name, backend, style_prompt)
            VALUES ('voice_legacy', 'proj_legacy', 'Legacy narrator', 'mock', NULL);
            INSERT INTO export_packages (id, project_id, format, status, output_path, manifest_path)
            VALUES ('export_legacy', 'proj_legacy', 'wav', 'succeeded', '/tmp/out', '/tmp/manifest');
            INSERT INTO chapter_renders (id, chapter_id, status, speech_path, manifest_path, duration_ms)
            VALUES ('chapter_render_legacy', 'chap_legacy', 'succeeded', '/tmp/speech.wav', '/tmp/manifest.json', 1200);
            """
        )

    database = Database(f"sqlite:///{database_path}")
    database.create_schema()

    with sqlite3.connect(database_path) as connection:
        voice_columns = {row[1] for row in connection.execute("PRAGMA table_info(voice_profiles)")}
        export_columns = {row[1] for row in connection.execute("PRAGMA table_info(export_packages)")}
        chapter_render_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(chapter_renders)")
        }
        provider_voice_id = connection.execute(
            "SELECT provider_voice_id FROM voice_profiles WHERE id = 'voice_legacy'"
        ).fetchone()[0]
        archive_path = connection.execute(
            "SELECT archive_path FROM export_packages WHERE id = 'export_legacy'"
        ).fetchone()[0]
        render_mode, ambience_stem_path, mixed_audio_path = connection.execute(
            "SELECT render_mode, ambience_stem_path, mixed_audio_path "
            "FROM chapter_renders WHERE id = 'chapter_render_legacy'"
        ).fetchone()

    assert "provider_voice_id" in voice_columns
    assert "archive_path" in export_columns
    assert {"render_mode", "ambience_stem_path", "mixed_audio_path"} <= chapter_render_columns
    assert provider_voice_id == ""
    assert archive_path is None
    assert render_mode == "speech_only"
    assert ambience_stem_path is None
    assert mixed_audio_path is None
