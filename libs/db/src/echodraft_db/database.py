from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


class Database:
    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///"),).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(url, connect_args=connect_args)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        self._repair_sqlite_schema_drift()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.sessions()
        try:
            yield session
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
