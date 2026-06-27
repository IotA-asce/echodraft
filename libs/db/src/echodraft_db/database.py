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
        if not repairs:
            return
        with self.engine.begin() as connection:
            for statement in repairs:
                connection.execute(text(statement))
