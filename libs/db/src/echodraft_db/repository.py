import json
from datetime import UTC, datetime
from uuid import uuid4

from echodraft_domain import Job, JobState, Project, ProjectCreate, RightsStatus
from sqlalchemy import select

from .database import Database
from .models import JobRecord, ProjectRecord, RightsDeclarationRecord


def _project(record: ProjectRecord) -> Project:
    return Project.model_validate(
        {
            "id": record.id,
            "title": record.title,
            "author": record.author,
            "description": record.description,
            "rightsStatus": RightsStatus(record.rights_status),
            "status": record.status,
            "artifactPath": record.artifact_path,
            "createdAt": record.created_at,
            "updatedAt": record.updated_at,
        }
    )


def _job(record: JobRecord) -> Job:
    return Job.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "jobType": record.job_type,
            "targetId": record.target_id,
            "status": JobState(record.status),
            "progress": json.loads(record.progress_json),
            "errorMessage": record.error_message,
            "createdAt": record.created_at,
            "startedAt": record.started_at,
            "finishedAt": record.finished_at,
        }
    )


class ProjectRepository:
    def __init__(self, database: Database, artifact_root: str) -> None:
        self.database = database
        self.artifact_root = artifact_root

    def create(
        self, payload: ProjectCreate, artifact_path: str, project_id: str | None = None
    ) -> Project:
        project_id = project_id or f"proj_{uuid4().hex[:16]}"
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = ProjectRecord(
                id=project_id,
                title=payload.title.strip(),
                author=payload.author.strip() if payload.author else None,
                description=payload.description.strip() if payload.description else None,
                rights_status=payload.rights_status.value,
                status="draft",
                artifact_path=artifact_path,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.add(
                RightsDeclarationRecord(
                    id=f"rights_{uuid4().hex[:16]}",
                    project_id=project_id,
                    declaration_type="self_attested",
                    status=payload.rights_status.value,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
            return _project(record)

    def list(self) -> list[Project]:
        with self.database.session() as session:
            return [_project(item) for item in session.scalars(select(ProjectRecord).order_by(ProjectRecord.created_at.desc()))]


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, job_type: str, project_id: str | None = None, target_id: str | None = None) -> Job:
        now = datetime.now(UTC)
        record = JobRecord(
            id=f"job_{uuid4().hex[:16]}",
            project_id=project_id,
            job_type=job_type,
            target_id=target_id,
            status=JobState.QUEUED.value,
            created_at=now,
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return _job(record)

    def get(self, job_id: str) -> Job | None:
        with self.database.session() as session:
            record = session.get(JobRecord, job_id)
            return _job(record) if record else None

    def transition(self, job_id: str, target: JobState, error_message: str | None = None) -> Job:
        allowed = {
            JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
            JobState.RUNNING: {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
            JobState.SUCCEEDED: set(),
            JobState.FAILED: set(),
            JobState.CANCELLED: set(),
        }
        with self.database.session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                raise KeyError(job_id)
            current = JobState(record.status)
            if target not in allowed[current]:
                raise ValueError(f"Cannot transition {current.value} to {target.value}.")
            now = datetime.now(UTC)
            record.status = target.value
            if target is JobState.RUNNING:
                record.started_at = now
            if target in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
                record.finished_at = now
            record.error_message = error_message
            session.commit()
            return _job(record)
