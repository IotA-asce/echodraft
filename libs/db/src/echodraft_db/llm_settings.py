from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from .database import Database
from .models import LlmSettingsRecord

_SINGLETON_ID = 1


@dataclass(frozen=True)
class LlmSettingsRow:
    provider: str
    base_url: str | None
    model: str | None
    api_key: str | None
    cloud_consent: bool
    updated_at: datetime | None


def _row(record: LlmSettingsRecord) -> LlmSettingsRow:
    return LlmSettingsRow(
        provider=record.provider,
        base_url=record.base_url,
        model=record.model,
        api_key=record.api_key,
        cloud_consent=record.cloud_consent,
        updated_at=record.updated_at,
    )


class LlmSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self) -> LlmSettingsRow:
        with self.database.session() as session:
            record = session.get(LlmSettingsRecord, _SINGLETON_ID)
            if record is None:
                record = LlmSettingsRecord(id=_SINGLETON_ID, provider="ollama", cloud_consent=False)
                session.add(record)
                try:
                    session.commit()
                except IntegrityError:
                    # Concurrent first-access: pipeline stages construct LocalLlmService
                    # from inside a ThreadPoolExecutor fan-out, so two threads can both
                    # observe `record is None` on a fresh DB and race to insert id=1. The
                    # loser rolls back and re-reads the winner's row instead of raising.
                    session.rollback()
                    winner = session.get(LlmSettingsRecord, _SINGLETON_ID)
                    assert winner is not None  # only reachable if the winner's insert committed
                    record = winner
            return _row(record)

    def update(
        self,
        *,
        provider: str,
        base_url: str | None,
        model: str | None,
        api_key: str | None,
        cloud_consent: bool,
    ) -> LlmSettingsRow:
        with self.database.session() as session:
            record = session.get(LlmSettingsRecord, _SINGLETON_ID)
            if record is None:
                record = LlmSettingsRecord(id=_SINGLETON_ID)
                session.add(record)
            record.provider = provider
            record.base_url = base_url
            record.model = model
            record.api_key = api_key
            record.cloud_consent = cloud_consent
            record.updated_at = datetime.now(UTC)
            session.commit()
            return _row(record)
