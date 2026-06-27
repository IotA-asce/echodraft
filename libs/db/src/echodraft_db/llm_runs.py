import json
from datetime import UTC, datetime

from echodraft_domain import LlmRun
from sqlalchemy import select

from .database import Database
from .models import LlmRunRecord


def _llm_run(record: LlmRunRecord) -> LlmRun:
    return LlmRun.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "sourceDocumentId": record.source_document_id,
            "provider": record.provider,
            "model": record.model,
            "task": record.task,
            "status": record.status,
            "promptPath": record.prompt_path,
            "responsePath": record.response_path,
            "schema": json.loads(record.schema_json),
            "result": json.loads(record.result_json) if record.result_json else None,
            "errorMessage": record.error_message,
            "retries": record.retries,
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
        }
    )


class LlmRunRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        record_id: str,
        *,
        project_id: str | None,
        source_document_id: str | None,
        provider: str,
        model: str,
        task: str,
        prompt_path: str | None,
        schema: dict[str, object],
    ) -> LlmRun:
        with self.database.session() as session:
            record = LlmRunRecord(
                id=record_id,
                project_id=project_id,
                source_document_id=source_document_id,
                provider=provider,
                model=model,
                task=task,
                status="running",
                prompt_path=prompt_path,
                schema_json=json.dumps(schema),
                started_at=datetime.now(UTC),
            )
            session.add(record)
            session.commit()
            return _llm_run(record)

    def complete(
        self,
        run_id: str,
        *,
        status: str,
        response_path: str | None = None,
        result: dict[str, object] | None = None,
        error_message: str | None = None,
        retries: int | None = None,
    ) -> LlmRun:
        with self.database.session() as session:
            record = session.get(LlmRunRecord, run_id)
            if not record:
                raise KeyError(run_id)
            record.status = status
            record.response_path = response_path
            record.result_json = json.dumps(result) if result is not None else None
            record.error_message = error_message
            if retries is not None:
                record.retries = retries
            record.completed_at = datetime.now(UTC)
            session.commit()
            return _llm_run(record)

    def get(self, run_id: str) -> LlmRun | None:
        with self.database.session() as session:
            record = session.get(LlmRunRecord, run_id)
            return _llm_run(record) if record else None

    def list_for_project(self, project_id: str) -> list[LlmRun]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(LlmRunRecord)
                    .where(LlmRunRecord.project_id == project_id)
                    .order_by(LlmRunRecord.started_at.desc())
                )
            )
        return [_llm_run(record) for record in records]
