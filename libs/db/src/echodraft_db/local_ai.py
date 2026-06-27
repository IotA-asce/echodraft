from datetime import UTC, datetime
from uuid import uuid4

from echodraft_domain import LocalAiInstallation, LocalAiInstallJob
from sqlalchemy import select

from .database import Database
from .models import ModelInstallationRecord, ModelInstallJobRecord


def _installation(record: ModelInstallationRecord) -> LocalAiInstallation:
    return LocalAiInstallation.model_validate(
        {
            "id": record.id,
            "modelKey": record.model_key,
            "displayName": record.display_name,
            "capability": record.capability,
            "provider": record.provider,
            "version": record.version,
            "installPath": record.install_path,
            "status": record.status,
            "installedAt": record.installed_at,
            "lastVerifiedAt": record.last_verified_at,
            "sizeBytes": record.size_bytes,
            "licenseSummary": record.license_summary,
            "errorMessage": record.error_message,
        }
    )


def _install_job(record: ModelInstallJobRecord) -> LocalAiInstallJob:
    return LocalAiInstallJob.model_validate(
        {
            "id": record.id,
            "jobId": record.job_id,
            "modelKey": record.model_key,
            "status": record.status,
            "progressPercent": record.progress_percent,
            "currentStep": record.current_step,
            "logsPath": record.logs_path,
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
            "errorMessage": record.error_message,
        }
    )


class LocalAiRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def installations(self) -> list[LocalAiInstallation]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(ModelInstallationRecord).order_by(ModelInstallationRecord.model_key)
                )
            )
            return [_installation(record) for record in records]

    def installation(self, model_key: str) -> LocalAiInstallation | None:
        with self.database.session() as session:
            record = session.scalar(
                select(ModelInstallationRecord).where(
                    ModelInstallationRecord.model_key == model_key
                )
            )
            return _installation(record) if record else None

    def upsert_installation(
        self,
        *,
        model_key: str,
        display_name: str,
        capability: str,
        provider: str,
        status: str,
        version: str | None = None,
        install_path: str | None = None,
        size_bytes: int | None = None,
        license_summary: str | None = None,
        error_message: str | None = None,
    ) -> LocalAiInstallation:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ModelInstallationRecord).where(
                    ModelInstallationRecord.model_key == model_key
                )
            )
            if not record:
                record = ModelInstallationRecord(
                    id=f"model_{uuid4().hex[:16]}",
                    model_key=model_key,
                    display_name=display_name,
                    capability=capability,
                    provider=provider,
                    status=status,
                    installed_at=now if status == "installed" else None,
                )
                session.add(record)
            record.display_name = display_name
            record.capability = capability
            record.provider = provider
            record.version = version
            record.install_path = install_path
            record.status = status
            if status == "installed" and not record.installed_at:
                record.installed_at = now
            record.last_verified_at = now
            record.size_bytes = size_bytes
            record.license_summary = license_summary
            record.error_message = error_message
            session.commit()
            return _installation(record)

    def remove_installation(self, model_key: str) -> bool:
        with self.database.session() as session:
            record = session.scalar(
                select(ModelInstallationRecord).where(
                    ModelInstallationRecord.model_key == model_key
                )
            )
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    def create_install_job(self, job_id: str, model_key: str, logs_path: str) -> LocalAiInstallJob:
        record = ModelInstallJobRecord(
            id=f"modeljob_{uuid4().hex[:16]}",
            job_id=job_id,
            model_key=model_key,
            status="queued",
            progress_percent=0,
            logs_path=logs_path,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return _install_job(record)

    def update_install_job(
        self,
        job_id: str,
        *,
        status: str,
        progress_percent: int | None = None,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> LocalAiInstallJob:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(ModelInstallJobRecord).where(ModelInstallJobRecord.job_id == job_id)
            )
            if not record:
                raise KeyError(job_id)
            record.status = status
            if progress_percent is not None:
                record.progress_percent = progress_percent
            if current_step is not None:
                record.current_step = current_step
            if status == "running" and record.started_at is None:
                record.started_at = now
            if status in {"succeeded", "failed", "cancelled"}:
                record.completed_at = now
            record.error_message = error_message
            session.commit()
            return _install_job(record)

    def install_job(self, job_id: str) -> LocalAiInstallJob | None:
        with self.database.session() as session:
            record = session.scalar(
                select(ModelInstallJobRecord).where(ModelInstallJobRecord.job_id == job_id)
            )
            return _install_job(record) if record else None
