from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class Database:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///"),).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        connect_args: dict[str, Any] = (
            {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        )
        self.engine: Engine = create_engine(url, connect_args=connect_args)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
                # Applied on every pooled connection: WAL + a generous busy_timeout keep
                # concurrent readers/writers from tripping "database is locked", and
                # foreign_keys=ON enforces referential integrity SQLite ignores by default.
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._repair_sqlite_schema_drift()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.sessions()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _repair_sqlite_schema_drift(self) -> None:
        """Apply safe, idempotent repairs for pre-migration local SQLite DBs.

        Early alpha builds created tables directly with SQLAlchemy metadata and
        did not stamp or run Alembic revisions on startup. `create_all()` does
        not add new columns to existing tables, so older local databases can be
        missing columns introduced by later metadata. Keep this narrowly scoped
        to additive, non-destructive repairs required by current models.
        """
        if self.engine.dialect.name != "sqlite":
            return
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        repairs: list[str] = []
        if "voice_profiles" in tables:
            columns = {column["name"] for column in inspector.get_columns("voice_profiles")}
            if "provider_voice_id" not in columns:
                repairs.append(
                    "ALTER TABLE voice_profiles "
                    "ADD COLUMN provider_voice_id VARCHAR(200) NOT NULL DEFAULT ''"
                )
        if "export_packages" in tables:
            columns = {column["name"] for column in inspector.get_columns("export_packages")}
            if "archive_path" not in columns:
                repairs.append("ALTER TABLE export_packages ADD COLUMN archive_path TEXT")
            if "created_at" not in columns:
                repairs.append("ALTER TABLE export_packages ADD COLUMN created_at TIMESTAMP")
        if "segment_renders" in tables:
            columns = {column["name"] for column in inspector.get_columns("segment_renders")}
            if "created_at" not in columns:
                repairs.append("ALTER TABLE segment_renders ADD COLUMN created_at TIMESTAMP")
            indexes = {index["name"] for index in inspector.get_indexes("segment_renders")}
            if "uq_segment_renders_succeeded_key" not in indexes:
                # Mirror migration 0024: dedupe append-only history (UPDATE to 'superseded',
                # never DELETE) before creating the partial unique index. Idempotent.
                repairs.append(
                    "UPDATE segment_renders SET status = 'superseded' "
                    "WHERE status = 'succeeded' AND id NOT IN ("
                    "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
                    "PARTITION BY segment_id, render_key "
                    "ORDER BY created_at DESC, rowid DESC) AS rn "
                    "FROM segment_renders WHERE status = 'succeeded') ranked "
                    "WHERE ranked.rn = 1)"
                )
                repairs.append(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_segment_renders_succeeded_key "
                    "ON segment_renders (segment_id, render_key) WHERE status = 'succeeded'"
                )
        if "chapter_renders" in tables:
            columns = {column["name"] for column in inspector.get_columns("chapter_renders")}
            if "render_mode" not in columns:
                repairs.append(
                    "ALTER TABLE chapter_renders "
                    "ADD COLUMN render_mode VARCHAR(32) NOT NULL DEFAULT 'speech_only'"
                )
            if "ambience_stem_path" not in columns:
                repairs.append("ALTER TABLE chapter_renders ADD COLUMN ambience_stem_path TEXT")
            if "mixed_audio_path" not in columns:
                repairs.append("ALTER TABLE chapter_renders ADD COLUMN mixed_audio_path TEXT")
            if "created_at" not in columns:
                repairs.append("ALTER TABLE chapter_renders ADD COLUMN created_at TIMESTAMP")
        if "ambience_assets" in tables:
            columns = {column["name"] for column in inspector.get_columns("ambience_assets")}
            if "asset_type" not in columns:
                repairs.append(
                    "ALTER TABLE ambience_assets "
                    "ADD COLUMN asset_type VARCHAR(32) NOT NULL DEFAULT 'ambience'"
                )
            if "duration_ms" not in columns:
                repairs.append("ALTER TABLE ambience_assets ADD COLUMN duration_ms INTEGER")
        if "ambience_cues" in tables:
            columns = {column["name"] for column in inspector.get_columns("ambience_cues")}
            cue_columns = {
                "cue_type": "VARCHAR(32) NOT NULL DEFAULT 'ambience'",
                "start_ms": "INTEGER NOT NULL DEFAULT 0",
                "ducking": "BOOLEAN NOT NULL DEFAULT 1",
                "render_mode": "VARCHAR(32) NOT NULL DEFAULT 'light'",
            }
            for column_name, column_type in cue_columns.items():
                if column_name not in columns:
                    repairs.append(
                        f"ALTER TABLE ambience_cues ADD COLUMN {column_name} {column_type}"
                    )
        if "characters" in tables:
            columns = {column["name"] for column in inspector.get_columns("characters")}
            character_columns = {
                "canonical_name": "VARCHAR(200)",
                "traits_json": "TEXT NOT NULL DEFAULT '[]'",
                "first_seen_source_id": "VARCHAR(64)",
                "first_seen_chapter_id": "VARCHAR(64)",
                "first_seen_segment_id": "VARCHAR(64)",
                "merge_history_json": "TEXT NOT NULL DEFAULT '[]'",
                "split_history_json": "TEXT NOT NULL DEFAULT '[]'",
                "user_locked": "BOOLEAN NOT NULL DEFAULT 0",
                "lock_reason": "TEXT",
                "merged_into_character_id": "VARCHAR(64)",
            }
            for column_name, column_type in character_columns.items():
                if column_name not in columns:
                    repairs.append(f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}")
        if "speaker_attributions" in tables:
            columns = {column["name"] for column in inspector.get_columns("speaker_attributions")}
            attribution_columns = {
                "project_id": "VARCHAR(64)",
                "segment_id": "VARCHAR(64)",
                "character_id": "VARCHAR(64)",
                "speaker_name": "VARCHAR(200)",
                "method": "VARCHAR(64) NOT NULL DEFAULT 'deterministic'",
                "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
                "confidence": "FLOAT NOT NULL DEFAULT 0",
                "status": "VARCHAR(32) NOT NULL DEFAULT 'needs_review'",
                "user_locked": "BOOLEAN NOT NULL DEFAULT 0",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            }
            for column_name, column_type in attribution_columns.items():
                if column_name not in columns:
                    repairs.append(
                        f"ALTER TABLE speaker_attributions ADD COLUMN {column_name} {column_type}"
                    )
        if "segment_directions" in tables:
            columns = {column["name"] for column in inspector.get_columns("segment_directions")}
            direction_columns = {
                "project_id": "VARCHAR(64)",
                "direction_json": "TEXT NOT NULL DEFAULT '{}'",
                "source": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
                "user_locked": "BOOLEAN NOT NULL DEFAULT 0",
                "direction_fingerprint": "VARCHAR(64) NOT NULL DEFAULT ''",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            }
            for column_name, column_type in direction_columns.items():
                if column_name not in columns:
                    repairs.append(
                        f"ALTER TABLE segment_directions ADD COLUMN {column_name} {column_type}"
                    )
        for table_name in ("chapters", "scenes", "segments"):
            if table_name in tables:
                columns = {column["name"] for column in inspector.get_columns(table_name)}
                if "parser_evidence_json" not in columns:
                    repairs.append(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN parser_evidence_json TEXT NOT NULL DEFAULT '{}'"
                    )
                if "user_locked" not in columns:
                    repairs.append(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN user_locked BOOLEAN NOT NULL DEFAULT 0"
                    )
                if "lock_reason" not in columns:
                    repairs.append(f"ALTER TABLE {table_name} ADD COLUMN lock_reason TEXT")
        if not repairs:
            return
        with self.engine.begin() as connection:
            for statement in repairs:
                connection.execute(text(statement))
