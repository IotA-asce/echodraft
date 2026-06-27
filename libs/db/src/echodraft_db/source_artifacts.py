import json
from pathlib import Path

from echodraft_domain import (
    CanonicalSpan,
    CleaningRun,
    OcrPageResult,
    OcrRun,
    ParserWarning,
    SourcePage,
    TextCleanlinessIssue,
)
from sqlalchemy import delete, select

from .database import Database
from .models import (
    CanonicalSpanRecord,
    CleaningRunRecord,
    OcrPageResultRecord,
    OcrRunRecord,
    SourcePageRecord,
    TextCleanlinessIssueRecord,
)


def _warnings(payload: str) -> list[ParserWarning]:
    return [ParserWarning.model_validate(item) for item in json.loads(payload)]


def _source_page(record: SourcePageRecord) -> SourcePage:
    preview = None
    if record.selected_text_path and Path(record.selected_text_path).is_file():
        preview = Path(record.selected_text_path).read_text(encoding="utf-8")[:1200]
    return SourcePage.model_validate(
        {
            "id": record.id,
            "sourceDocumentId": record.source_document_id,
            "pageNumber": record.page_number,
            "imagePath": record.image_path,
            "embeddedTextPath": record.embedded_text_path,
            "selectedTextPath": record.selected_text_path,
            "extractionMethod": record.extraction_method,
            "confidence": record.confidence,
            "warnings": _warnings(record.warnings_json),
            "preview": preview,
        }
    )


def _ocr_run(record: OcrRunRecord) -> OcrRun:
    return OcrRun.model_validate(
        {
            "id": record.id,
            "sourceDocumentId": record.source_document_id,
            "provider": record.provider,
            "status": record.status,
            "settings": json.loads(record.settings_json),
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
            "errorMessage": record.error_message,
        }
    )


def _ocr_page_result(record: OcrPageResultRecord) -> OcrPageResult:
    return OcrPageResult.model_validate(
        {
            "id": record.id,
            "ocrRunId": record.ocr_run_id,
            "sourcePageId": record.source_page_id,
            "pageNumber": record.page_number,
            "textPath": record.text_path,
            "jsonPath": record.json_path,
            "confidence": record.confidence,
            "warnings": _warnings(record.warnings_json),
        }
    )


def _canonical_span(record: CanonicalSpanRecord) -> CanonicalSpan:
    return CanonicalSpan.model_validate(
        {
            "id": record.id,
            "sourceDocumentId": record.source_document_id,
            "pageNumber": record.page_number,
            "canonicalStartOffset": record.canonical_start_offset,
            "canonicalEndOffset": record.canonical_end_offset,
            "sourceTextHash": record.source_text_hash,
            "bbox": json.loads(record.bbox_json) if record.bbox_json else None,
            "extractionMethod": record.extraction_method,
            "confidence": record.confidence,
        }
    )


def _cleaning_run(record: CleaningRunRecord) -> CleaningRun:
    return CleaningRun.model_validate(
        {
            "id": record.id,
            "sourceDocumentId": record.source_document_id,
            "status": record.status,
            "manifestPath": record.manifest_path,
            "startedAt": record.started_at,
            "completedAt": record.completed_at,
            "errorMessage": record.error_message,
        }
    )


def _cleanliness_issue(record: TextCleanlinessIssueRecord) -> TextCleanlinessIssue:
    return TextCleanlinessIssue.model_validate(
        {
            "id": record.id,
            "sourceDocumentId": record.source_document_id,
            "canonicalSpanStart": record.canonical_span_start,
            "canonicalSpanEnd": record.canonical_span_end,
            "issueType": record.issue_type,
            "severity": record.severity,
            "suggestedFix": record.suggested_fix,
            "confidence": record.confidence,
            "status": record.status,
            "resolvedByUser": record.resolved_by_user,
        }
    )


class SourceArtifactRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def clear_source(self, source_id: str) -> None:
        with self.database.session() as session:
            page_ids = select(SourcePageRecord.id).where(
                SourcePageRecord.source_document_id == source_id
            )
            ocr_run_ids = select(OcrRunRecord.id).where(OcrRunRecord.source_document_id == source_id)
            session.execute(
                delete(OcrPageResultRecord).where(OcrPageResultRecord.ocr_run_id.in_(ocr_run_ids))
            )
            session.execute(delete(OcrRunRecord).where(OcrRunRecord.source_document_id == source_id))
            session.execute(
                delete(CanonicalSpanRecord).where(
                    CanonicalSpanRecord.source_document_id == source_id
                )
            )
            session.execute(
                delete(TextCleanlinessIssueRecord).where(
                    TextCleanlinessIssueRecord.source_document_id == source_id
                )
            )
            session.execute(
                delete(CleaningRunRecord).where(CleaningRunRecord.source_document_id == source_id)
            )
            session.execute(delete(SourcePageRecord).where(SourcePageRecord.id.in_(page_ids)))
            session.commit()

    def create_page(self, record: SourcePageRecord) -> SourcePageRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def create_ocr_run(self, record: OcrRunRecord) -> OcrRunRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def update_ocr_run(self, run_id: str, **fields: object) -> OcrRunRecord:
        with self.database.session() as session:
            record = session.get(OcrRunRecord, run_id)
            if not record:
                raise KeyError(run_id)
            for key, value in fields.items():
                setattr(record, key, value)
            session.commit()
            return record

    def create_ocr_page_result(self, record: OcrPageResultRecord) -> OcrPageResultRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def create_span(self, record: CanonicalSpanRecord) -> CanonicalSpanRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def pages(self, source_id: str) -> list[SourcePage]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(SourcePageRecord)
                    .where(SourcePageRecord.source_document_id == source_id)
                    .order_by(SourcePageRecord.page_number)
                )
            )
        return [_source_page(record) for record in records]

    def page(self, source_id: str, page_number: int) -> SourcePage | None:
        with self.database.session() as session:
            record = session.scalar(
                select(SourcePageRecord).where(
                    SourcePageRecord.source_document_id == source_id,
                    SourcePageRecord.page_number == page_number,
                )
            )
        return _source_page(record) if record else None

    def ocr_runs(self, source_id: str) -> list[OcrRun]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(OcrRunRecord)
                    .where(OcrRunRecord.source_document_id == source_id)
                    .order_by(OcrRunRecord.started_at.desc())
                )
            )
        return [_ocr_run(record) for record in records]

    def ocr_results(self, run_id: str) -> list[OcrPageResult]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(OcrPageResultRecord)
                    .where(OcrPageResultRecord.ocr_run_id == run_id)
                    .order_by(OcrPageResultRecord.page_number)
                )
            )
        return [_ocr_page_result(record) for record in records]

    def spans(self, source_id: str) -> list[CanonicalSpan]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CanonicalSpanRecord)
                    .where(CanonicalSpanRecord.source_document_id == source_id)
                    .order_by(CanonicalSpanRecord.canonical_start_offset)
                )
            )
        return [_canonical_span(record) for record in records]

    def create_cleaning_run(self, record: CleaningRunRecord) -> CleaningRunRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def update_cleaning_run(self, run_id: str, **fields: object) -> CleaningRunRecord:
        with self.database.session() as session:
            record = session.get(CleaningRunRecord, run_id)
            if not record:
                raise KeyError(run_id)
            for key, value in fields.items():
                setattr(record, key, value)
            session.commit()
            return record

    def cleaning_runs(self, source_id: str) -> list[CleaningRun]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(CleaningRunRecord)
                    .where(CleaningRunRecord.source_document_id == source_id)
                    .order_by(CleaningRunRecord.started_at.desc())
                )
            )
        return [_cleaning_run(record) for record in records]

    def create_cleanliness_issue(
        self, record: TextCleanlinessIssueRecord
    ) -> TextCleanlinessIssueRecord:
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def cleanliness_issues(self, source_id: str) -> list[TextCleanlinessIssue]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(TextCleanlinessIssueRecord)
                    .where(TextCleanlinessIssueRecord.source_document_id == source_id)
                    .order_by(TextCleanlinessIssueRecord.canonical_span_start)
                )
            )
        return [_cleanliness_issue(record) for record in records]

    def update_cleanliness_issue(
        self, issue_id: str, status: str | None, resolved_by_user: bool | None
    ) -> TextCleanlinessIssue | None:
        with self.database.session() as session:
            record = session.get(TextCleanlinessIssueRecord, issue_id)
            if not record:
                return None
            if status is not None:
                record.status = status
            if resolved_by_user is not None:
                record.resolved_by_user = resolved_by_user
            session.commit()
            return _cleanliness_issue(record)
