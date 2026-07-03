from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from sqlalchemy import func, select

from echodraft_api.jobs import InProcessJobRunner
from echodraft_db import CastMergeDecisionRepository, Database, JobRepository
from echodraft_db.models import CastMergeDecisionRecord, JobRecord, ProjectRecord
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
            CREATE TABLE characters (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64),
                display_name VARCHAR(200) NOT NULL,
                aliases_json TEXT NOT NULL,
                role_type VARCHAR(64) NOT NULL,
                confidence FLOAT NOT NULL,
                notes TEXT
            );
            INSERT INTO voice_profiles (id, project_id, name, backend, style_prompt)
            VALUES ('voice_legacy', 'proj_legacy', 'Legacy narrator', 'mock', NULL);
            INSERT INTO export_packages (id, project_id, format, status, output_path, manifest_path)
            VALUES ('export_legacy', 'proj_legacy', 'wav', 'succeeded', '/tmp/out', '/tmp/manifest');
            INSERT INTO chapter_renders (id, chapter_id, status, speech_path, manifest_path, duration_ms)
            VALUES ('chapter_render_legacy', 'chap_legacy', 'succeeded', '/tmp/speech.wav', '/tmp/manifest.json', 1200);
            INSERT INTO characters (id, project_id, display_name, aliases_json, role_type, confidence, notes)
            VALUES ('char_legacy', 'proj_legacy', 'Legacy cast', '[]', 'major', 1.0, NULL);
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
        character_columns = {row[1] for row in connection.execute("PRAGMA table_info(characters)")}
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
        traits_json, merge_history_json, user_locked = connection.execute(
            "SELECT traits_json, merge_history_json, user_locked "
            "FROM characters WHERE id = 'char_legacy'"
        ).fetchone()

    assert "provider_voice_id" in voice_columns
    assert "archive_path" in export_columns
    assert {"render_mode", "ambience_stem_path", "mixed_audio_path"} <= chapter_render_columns
    assert {
        "canonical_name",
        "traits_json",
        "first_seen_source_id",
        "first_seen_chapter_id",
        "first_seen_segment_id",
        "merge_history_json",
        "split_history_json",
        "user_locked",
        "lock_reason",
        "merged_into_character_id",
    } <= character_columns
    assert provider_voice_id == ""
    assert archive_path is None
    assert render_mode == "speech_only"
    assert ambience_stem_path is None
    assert mixed_audio_path is None
    assert traits_json == "[]"
    assert merge_history_json == "[]"
    assert user_locked == 0


def test_sqlite_engine_applies_concurrency_pragmas(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'pragmas.db'}")
    database.create_schema()
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000


def test_session_rolls_back_on_exception(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'rollback.db'}")
    database.create_schema()
    with pytest.raises(RuntimeError):
        with database.session() as session:
            session.add(
                JobRecord(
                    id="job_rollback",
                    project_id=None,
                    job_type="test.rollback",
                    target_id=None,
                    status="queued",
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()
            raise RuntimeError("boom")
    with database.session() as session:
        assert session.get(JobRecord, "job_rollback") is None


def test_cast_merge_decision_upsert_normalizes_name_pair(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'cast-merge.db'}")
    database.create_schema()
    with database.session() as session:
        session.add(
            ProjectRecord(
                id="proj_cast_merge",
                title="Cast Merge",
                author=None,
                description=None,
                rights_status="declared",
                status="draft",
                artifact_path=str(tmp_path / "artifacts"),
            )
        )
        session.commit()

    repository = CastMergeDecisionRepository(database)
    first = repository.record(
        "proj_cast_merge", "Bran", "Brandon", "rejected", "Different people."
    )
    second = repository.record(
        "proj_cast_merge", "Brandon", "Bran", "confirmed", "Same person."
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    decision = repository.decision_for("proj_cast_merge", "Bran", "Brandon")
    assert decision is not None
    assert decision.decision == "confirmed"
    assert decision.reason == "Same person."
    with database.session() as session:
        count = session.scalar(select(func.count()).select_from(CastMergeDecisionRecord))
    assert count == 1


def test_bounded_executor_keeps_second_job_queued(app) -> None:
    repository: JobRepository = app.state.container.jobs_repository
    runner = InProcessJobRunner(repository, max_workers=1)
    started = threading.Event()
    release = threading.Event()

    def blocking() -> None:
        started.set()
        assert release.wait(5)

    first = runner.submit("test.block", blocking)
    assert started.wait(2)
    second = runner.submit("test.block", lambda: None)
    time.sleep(0.1)
    assert repository.get(second.id).status is JobState.QUEUED
    assert repository.get(first.id).status is JobState.RUNNING
    release.set()
    for job_id in (first.id, second.id):
        for _ in range(200):
            if repository.get(job_id).status is JobState.SUCCEEDED:
                break
            time.sleep(0.02)
        assert repository.get(job_id).status is JobState.SUCCEEDED
