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
