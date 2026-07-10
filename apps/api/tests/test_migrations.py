"""Guard that Alembic migrations produce exactly the schema the models declare.

The app bootstraps schema via create_all + repair, not Alembic, so this test is the
only thing keeping the migration history honest.
"""

from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.command import upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from echodraft_db.database import Database
from echodraft_db.models import Base
from echodraft_domain import DirectionProfile, SegmentDirection

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "libs" / "db" / "alembic.ini"
# Alembic's own bookkeeping table is not part of the domain metadata; ignore it.
IGNORED_TABLES = {"alembic_version"}


def _touches_ignored_table(entry: Any) -> bool:
    elements = entry if isinstance(entry, (list, tuple)) else [entry]
    for element in elements:
        name = getattr(element, "name", None)
        table = getattr(element, "table", None)
        table_name = getattr(table, "name", None)
        if name in IGNORED_TABLES or table_name in IGNORED_TABLES:
            return True
    return False


def test_alembic_head_matches_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    monkeypatch.setenv("ECHODRAFT_DATABASE_URL", url)

    config = Config(str(ALEMBIC_INI))
    upgrade(config, "head")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    drift = [entry for entry in diff if not _touches_ignored_table(entry)]
    assert not drift, "Alembic migrations diverged from models:\n" + "\n".join(
        repr(entry) for entry in drift
    )


def test_alembic_head_creates_automatic_casting_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'automatic-casting-head.db'}"
    monkeypatch.setenv("ECHODRAFT_DATABASE_URL", url)

    config = Config(str(ALEMBIC_INI))
    upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        decision_columns = {
            column["name"] for column in inspector.get_columns("casting_decisions")
        }
        assert {
            "voice_catalog_entry_id",
            "candidate_scores_json",
            "algorithm_version",
            "catalog_version",
            "superseded_by_id",
        } <= decision_columns
        decision_indexes = {
            index["name"] for index in inspector.get_indexes("casting_decisions")
        }
        assert {
            "ix_casting_decisions_project_role",
            "uq_casting_decisions_active_character",
            "uq_casting_decisions_active_narrator",
        } <= decision_indexes
        settings_columns = {
            column["name"]
            for column in inspector.get_columns("project_production_settings")
        }
        assert {
            "narrator_casting_decision_id",
            "casting_style_preset",
            "auto_cast_enabled",
        } <= settings_columns
        assignment_columns = {
            column["name"]
            for column in inspector.get_columns("character_voice_assignments")
        }
        assert {"user_locked", "locked_reason", "casting_decision_id"} <= assignment_columns
        assignment_indexes = {
            index["name"]
            for index in inspector.get_indexes("character_voice_assignments")
        }
        assert "ix_character_voice_assignments_casting_decision_id" in assignment_indexes
    finally:
        engine.dispose()


def test_alembic_head_creates_cast_graph_tables_and_character_enrichment_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'cast-graph-head.db'}"
    monkeypatch.setenv("ECHODRAFT_DATABASE_URL", url)

    config = Config(str(ALEMBIC_INI))
    upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert {"character_mentions", "cast_graph_decisions"} <= set(inspector.get_table_names())

        character_columns = {column["name"] for column in inspector.get_columns("characters")}
        assert {"relationships_json", "speaking_style_json"} <= character_columns

        mention_columns = {column["name"] for column in inspector.get_columns("character_mentions")}
        assert {
            "window_id",
            "normalized_key",
            "segment_ids_json",
            "traits_json",
            "relationships_json",
            "metadata_json",
        } <= mention_columns

        decision_columns = {
            column["name"] for column in inspector.get_columns("cast_graph_decisions")
        }
        assert {
            "source_key",
            "target_character_id",
            "evidence_segment_ids_json",
            "metadata_json",
        } <= decision_columns

        mention_indexes = {index["name"] for index in inspector.get_indexes("character_mentions")}
        assert {
            "ix_character_mentions_project_id",
            "ix_character_mentions_scene_id",
            "ix_character_mentions_window_id",
            "ix_character_mentions_normalized_key",
            "ix_character_mentions_source_document_id",
            "ix_character_mentions_llm_run_id",
        } <= mention_indexes

        decision_indexes = {
            index["name"] for index in inspector.get_indexes("cast_graph_decisions")
        }
        assert {
            "ix_cast_graph_decisions_project_id",
            "ix_cast_graph_decisions_source_key",
            "ix_cast_graph_decisions_target_character_id",
            "ix_cast_graph_decisions_llm_run_id",
        } <= decision_indexes
    finally:
        engine.dispose()


def test_sqlite_repair_adds_segment_direction_evidence_json(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE segment_directions ("
                "segment_id VARCHAR(64) PRIMARY KEY, "
                "project_id VARCHAR(64), "
                "direction_json TEXT NOT NULL DEFAULT '{}', "
                "source VARCHAR(32) NOT NULL DEFAULT 'manual', "
                "user_locked BOOLEAN NOT NULL DEFAULT 0, "
                "direction_fingerprint VARCHAR(64) NOT NULL DEFAULT '', "
                "created_at DATETIME, "
                "updated_at DATETIME"
                ")"
            )
        )

    database.create_schema()

    columns = {column["name"] for column in inspect(database.engine).get_columns("segment_directions")}
    assert "evidence_json" in columns


def test_sqlite_create_schema_repairs_characters_and_creates_cast_graph_tables(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy-cast-graph.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE characters ("
                "id VARCHAR(64) PRIMARY KEY, "
                "project_id VARCHAR(64), "
                "display_name VARCHAR(200) NOT NULL, "
                "aliases_json TEXT NOT NULL DEFAULT '[]', "
                "role_type VARCHAR(32) NOT NULL DEFAULT 'supporting', "
                "confidence FLOAT NOT NULL DEFAULT 0, "
                "notes TEXT"
                ")"
            )
        )

    database.create_schema()

    inspector = inspect(database.engine)
    assert {"character_mentions", "cast_graph_decisions"} <= set(inspector.get_table_names())

    character_columns = {column["name"] for column in inspector.get_columns("characters")}
    assert {"relationships_json", "speaking_style_json"} <= character_columns


def test_segment_direction_without_evidence_deserializes_as_empty() -> None:
    row = SegmentDirection.model_validate(
        {
            "segmentId": "seg_1",
            "projectId": "proj_1",
            "direction": DirectionProfile(scopeType="segment", scopeId="seg_1"),
            "source": "inferred",
            "userLocked": False,
            "directionFingerprint": "abc",
            "createdAt": "2026-07-05T00:00:00Z",
            "updatedAt": "2026-07-05T00:00:00Z",
        }
    )

    assert row.evidence == {}


def test_alembic_head_creates_grouped_review_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'review-tasks-head.db'}"
    monkeypatch.setenv("ECHODRAFT_DATABASE_URL", url)
    config = Config(str(ALEMBIC_INI))
    upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert "review_tasks" in inspector.get_table_names()
        task_columns = {
            column["name"] for column in inspector.get_columns("review_tasks")
        }
        assert {
            "cause_key",
            "scope_type",
            "member_count",
            "member_refs_json",
            "evidence_json",
            "status",
        } <= task_columns
        for table in ("chapters", "scenes", "segments"):
            columns = {column["name"] for column in inspector.get_columns(table)}
            assert {"auto_accepted", "decision_tier"} <= columns
        attribution_columns = {
            column["name"]
            for column in inspector.get_columns("speaker_attributions")
        }
        assert {"auto_accepted", "decision_tier", "review_task_id"} <= attribution_columns
        indexes = {index["name"] for index in inspector.get_indexes("review_tasks")}
        assert {
            "ix_review_tasks_project_status",
            "uq_review_tasks_open_cause",
        } <= indexes
    finally:
        engine.dispose()


def test_sqlite_repair_adds_confidence_columns_to_legacy_tables(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy-confidence.db'}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE chapters ("
                "id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64), "
                "order_index INTEGER, title VARCHAR(512), start_offset INTEGER, "
                "end_offset INTEGER, confidence FLOAT, status VARCHAR(32))"
            )
        )
    database.create_schema()

    inspector = inspect(database.engine)
    columns = {column["name"] for column in inspector.get_columns("chapters")}
    assert {"auto_accepted", "decision_tier"} <= columns
    assert "review_tasks" in inspector.get_table_names()
