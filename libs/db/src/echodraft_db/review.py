import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from .database import Database
from .models import CommentRecord, IssueRecord, PatchAttemptRecord


class ReviewRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def issues(
        self, project_id: str, status: str | None = None, segment_id: str | None = None
    ) -> list[IssueRecord]:
        with self.database.session() as session:
            query = select(IssueRecord).where(IssueRecord.project_id == project_id)
            if status:
                query = query.where(IssueRecord.status == status)
            if segment_id:
                query = query.where(IssueRecord.segment_id == segment_id)
            return list(session.scalars(query.order_by(IssueRecord.created_at.desc())))

    def create_issue(
        self,
        project_id: str,
        category: str,
        severity: str,
        title: str,
        description: str,
        chapter_id: str | None = None,
        segment_id: str | None = None,
        metadata: dict[str, object] | None = None,
        dedupe_key: str | None = None,
    ) -> IssueRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            if dedupe_key:
                existing = session.scalar(
                    select(IssueRecord).where(IssueRecord.dedupe_key == dedupe_key)
                )
                if existing:
                    # A dedupe hit means the same check fired again, possibly with a
                    # different failure mode (e.g. severity escalated from warning to
                    # blocking). Refresh the content fields so the persisted row reflects
                    # the latest finding instead of freezing at first creation -- but leave
                    # `status`/`id`/`created_*` alone since those track reviewer decisions
                    # and identity, not the check's current output.
                    existing.severity = severity
                    existing.title = title
                    existing.description = description
                    existing.metadata_json = json.dumps(metadata or {}, sort_keys=True)
                    existing.updated_at = now
                    session.commit()
                    return existing
            record = IssueRecord(
                id=f"issue_{uuid4().hex[:16]}",
                project_id=project_id,
                chapter_id=chapter_id,
                segment_id=segment_id,
                severity=severity,
                category=category,
                title=title,
                description=description,
                status="open",
                metadata_json=json.dumps(metadata or {}, sort_keys=True),
                dedupe_key=dedupe_key,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.commit()
            return record

    def issue(self, issue_id: str) -> IssueRecord | None:
        with self.database.session() as session:
            return session.get(IssueRecord, issue_id)

    def issue_by_dedupe_key(self, dedupe_key: str) -> IssueRecord | None:
        with self.database.session() as session:
            return session.scalar(
                select(IssueRecord).where(IssueRecord.dedupe_key == dedupe_key)
            )

    def update_issue(
        self, issue_id: str, status: str | None, severity: str | None
    ) -> IssueRecord | None:
        with self.database.session() as session:
            record = session.get(IssueRecord, issue_id)
            if not record:
                return None
            if status:
                record.status = status
            if severity:
                record.severity = severity
            record.updated_at = datetime.now(UTC)
            session.commit()
            return record

    def merge_issue_metadata(
        self,
        issue_id: str,
        metadata: dict[str, object],
        status: str | None = None,
    ) -> IssueRecord | None:
        with self.database.session() as session:
            record = session.get(IssueRecord, issue_id)
            if not record:
                return None
            merged = json.loads(record.metadata_json)
            merged.update(metadata)
            record.metadata_json = json.dumps(merged, sort_keys=True)
            if status:
                record.status = status
            record.updated_at = datetime.now(UTC)
            session.commit()
            return record

    def comments(self, issue_id: str) -> list[CommentRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CommentRecord)
                    .where(CommentRecord.issue_id == issue_id)
                    .order_by(CommentRecord.created_at)
                )
            )

    def add_comment(self, issue_id: str, body: str, author: str) -> CommentRecord:
        record = CommentRecord(
            id=f"comment_{uuid4().hex[:16]}",
            issue_id=issue_id,
            body=body.strip(),
            author=author,
            created_at=datetime.now(UTC),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def add_patch_attempt(
        self,
        issue_id: str | None,
        segment_id: str,
        old_render_id: str | None,
        new_render_id: str,
        chapter_render_id: str,
    ) -> None:
        with self.database.session() as session:
            session.add(
                PatchAttemptRecord(
                    id=f"patch_{uuid4().hex[:16]}",
                    issue_id=issue_id,
                    segment_id=segment_id,
                    old_render_id=old_render_id,
                    new_render_id=new_render_id,
                    chapter_render_id=chapter_render_id,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
