import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from echodraft_domain import (
    Job,
    JobState,
    ParserWarning,
    Project,
    ProjectCreate,
    RightsStatus,
    SourceDocument,
)
from sqlalchemy import delete, select

from .database import Database
from .models import (
    ChapterRecord,
    CharacterRecord,
    CharacterVoiceAssignmentRecord,
    JobRecord,
    ProjectProductionSettingsRecord,
    PronunciationEntryRecord,
    ProjectRecord,
    RightsDeclarationRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRevisionRecord,
    SegmentProductionOverrideRecord,
    SourceDocumentRecord,
    VoiceProfileRecord,
)


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
            return [
                _project(item)
                for item in session.scalars(
                    select(ProjectRecord).order_by(ProjectRecord.created_at.desc())
                )
            ]

    def get(self, project_id: str) -> Project | None:
        with self.database.session() as session:
            record = session.get(ProjectRecord, project_id)
            return _project(record) if record else None


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self, job_type: str, project_id: str | None = None, target_id: str | None = None
    ) -> Job:
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

    def reconcile_interrupted(self) -> int:
        """In-process jobs cannot safely resume after restart; fail them with guidance."""
        with self.database.session() as session:
            records = list(
                session.scalars(select(JobRecord).where(JobRecord.status == JobState.RUNNING.value))
            )
            for record in records:
                record.status = JobState.FAILED.value
                record.error_message = (
                    "interrupted: restart the requested workflow from its last persisted artifact"
                )
                record.finished_at = datetime.now(UTC)
            session.commit()
            return len(records)

    def set_progress(self, job_id: str, progress: dict[str, object]) -> Job:
        with self.database.session() as session:
            record = session.get(JobRecord, job_id)
            if not record:
                raise KeyError(job_id)
            record.progress_json = json.dumps(progress)
            session.commit()
            return _job(record)

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


class SourceDocumentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, record: SourceDocumentRecord) -> None:
        with self.database.session() as session:
            session.add(record)
            session.commit()

    def update(self, source_id: str, **fields: object) -> SourceDocumentRecord:
        with self.database.session() as session:
            record = session.get(SourceDocumentRecord, source_id)
            if not record:
                raise KeyError(source_id)
            for key, value in fields.items():
                setattr(record, key, value)
            session.commit()
            return record

    def latest(self, project_id: str) -> SourceDocument | None:
        with self.database.session() as session:
            record = session.scalar(
                select(SourceDocumentRecord)
                .where(SourceDocumentRecord.project_id == project_id)
                .order_by(SourceDocumentRecord.imported_at.desc())
            )
            if not record:
                return None
            return SourceDocument.model_validate(
                {
                    "id": record.id,
                    "projectId": record.project_id,
                    "originalFilename": record.original_filename,
                    "mimeType": record.mime_type,
                    "checksum": record.checksum,
                    "importedAt": record.imported_at,
                    "rightsStatus": record.rights_status,
                    "parserVersion": record.parser_version,
                    "originalPath": record.original_path,
                    "canonicalPath": record.canonical_path,
                    "manifestPath": record.manifest_path,
                    "status": record.status,
                    "warnings": [
                        ParserWarning.model_validate(item)
                        for item in json.loads(record.warnings_json)
                    ],
                }
            )


class StructureRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def replace(self, project_id: str, hierarchy: list[dict[str, Any]]) -> None:
        with self.database.session() as session:
            chapter_ids = select(ChapterRecord.id).where(ChapterRecord.project_id == project_id)
            scene_ids = select(SceneRecord.id).where(SceneRecord.chapter_id.in_(chapter_ids))
            segment_ids = select(SegmentRecord.id).where(SegmentRecord.scene_id.in_(scene_ids))
            session.execute(
                delete(SegmentRevisionRecord).where(
                    SegmentRevisionRecord.segment_id.in_(segment_ids)
                )
            )
            session.execute(delete(SegmentRecord).where(SegmentRecord.scene_id.in_(scene_ids)))
            session.execute(delete(SceneRecord).where(SceneRecord.chapter_id.in_(chapter_ids)))
            session.execute(delete(ChapterRecord).where(ChapterRecord.project_id == project_id))
            for chapter in hierarchy:
                session.add(ChapterRecord(**chapter["record"]))
                for scene in chapter["scenes"]:
                    session.add(SceneRecord(**scene["record"]))
                    for segment in scene["segments"]:
                        session.add(SegmentRecord(**segment))
            session.commit()

    def chapters(self, project_id: str) -> list[ChapterRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(ChapterRecord)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(ChapterRecord.order_index)
                )
            )

    def chapter(self, chapter_id: str) -> ChapterRecord | None:
        with self.database.session() as session:
            return session.get(ChapterRecord, chapter_id)

    def scenes(self, chapter_id: str) -> list[SceneRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(SceneRecord)
                    .where(SceneRecord.chapter_id == chapter_id)
                    .order_by(SceneRecord.order_index)
                )
            )

    def segments(self, scene_id: str) -> list[SegmentRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(SegmentRecord)
                    .where(SegmentRecord.scene_id == scene_id)
                    .order_by(SegmentRecord.order_index)
                )
            )

    def update_segment(self, segment_id: str, text: str) -> SegmentRecord | None:
        with self.database.session() as session:
            record = session.get(SegmentRecord, segment_id)
            if not record:
                return None
            session.add(
                SegmentRevisionRecord(
                    id=f"segrev_{uuid4().hex[:16]}",
                    segment_id=segment_id,
                    revision=record.revision,
                    text_content=record.text_content,
                    created_at=datetime.now(UTC),
                )
            )
            record.text_content = text.strip()
            record.normalized_text = text.strip()
            record.revision += 1
            record.status = "needs_review"
            session.commit()
            return record

    def segment(self, segment_id: str) -> SegmentRecord | None:
        with self.database.session() as session:
            return session.get(SegmentRecord, segment_id)

    def revisions(self, segment_id: str) -> list[SegmentRevisionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(SegmentRevisionRecord)
                    .where(SegmentRevisionRecord.segment_id == segment_id)
                    .order_by(SegmentRevisionRecord.revision.desc())
                )
            )


class CastingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def characters(self, project_id: str) -> list[CharacterRecord]:
        with self.database.session() as s:
            return list(
                s.scalars(select(CharacterRecord).where(CharacterRecord.project_id == project_id))
            )

    def create_character(
        self,
        project_id: str,
        name: str,
        aliases: list[str],
        role: str,
        confidence: float,
        notes: str | None,
    ) -> CharacterRecord:
        with self.database.session() as s:
            record = CharacterRecord(
                id=f"char_{uuid4().hex[:16]}",
                project_id=project_id,
                display_name=name,
                aliases_json=json.dumps(aliases),
                role_type=role,
                confidence=confidence,
                notes=notes,
            )
            s.add(record)
            s.commit()
            return record

    def voices(self, project_id: str) -> list[VoiceProfileRecord]:
        with self.database.session() as s:
            return list(
                s.scalars(
                    select(VoiceProfileRecord).where(VoiceProfileRecord.project_id == project_id)
                )
            )

    def create_voice(
        self, project_id: str, name: str, backend: str, provider_voice_id: str, prompt: str | None
    ) -> VoiceProfileRecord:
        with self.database.session() as s:
            record = VoiceProfileRecord(
                id=f"voice_{uuid4().hex[:16]}",
                project_id=project_id,
                name=name,
                backend=backend,
                provider_voice_id=provider_voice_id,
                style_prompt=prompt,
            )
            s.add(record)
            s.commit()
            return record

    def voice(self, voice_id: str) -> VoiceProfileRecord | None:
        with self.database.session() as s:
            return s.get(VoiceProfileRecord, voice_id)

    def update_voice(
        self, voice_id: str, name: str | None, provider_voice_id: str | None, prompt: str | None
    ) -> VoiceProfileRecord | None:
        with self.database.session() as s:
            record = s.get(VoiceProfileRecord, voice_id)
            if not record:
                return None
            if name is not None:
                record.name = name
            if provider_voice_id is not None:
                record.provider_voice_id = provider_voice_id
            if prompt is not None:
                record.style_prompt = prompt
            s.commit()
            return record

    def delete_voice(self, voice_id: str) -> bool:
        with self.database.session() as s:
            record = s.get(VoiceProfileRecord, voice_id)
            if not record:
                return False
            assigned = s.scalar(
                select(CharacterVoiceAssignmentRecord).where(
                    CharacterVoiceAssignmentRecord.voice_profile_id == voice_id
                )
            )
            narrator = s.scalar(
                select(ProjectProductionSettingsRecord).where(
                    ProjectProductionSettingsRecord.narrator_voice_profile_id == voice_id
                )
            )
            overridden = s.scalar(
                select(SegmentProductionOverrideRecord).where(
                    SegmentProductionOverrideRecord.voice_profile_id == voice_id
                )
            )
            if assigned or narrator or overridden:
                raise ValueError("Voice profile is still used by production settings or an assignment.")
            s.delete(record)
            s.commit()
            return True

    def assign(self, character_id: str, voice_id: str) -> None:
        with self.database.session() as s:
            existing = s.scalar(
                select(CharacterVoiceAssignmentRecord).where(
                    CharacterVoiceAssignmentRecord.character_id == character_id
                )
            )
            if existing:
                existing.voice_profile_id = voice_id
            else:
                s.add(
                    CharacterVoiceAssignmentRecord(
                        id=f"assign_{uuid4().hex[:16]}",
                        character_id=character_id,
                        voice_profile_id=voice_id,
                    )
                )
            s.commit()

    def pronunciations(self, project_id: str) -> list[PronunciationEntryRecord]:
        with self.database.session() as s:
            return list(
                s.scalars(
                    select(PronunciationEntryRecord).where(
                        PronunciationEntryRecord.project_id == project_id
                    )
                )
            )

    def create_pronunciation(
        self, project_id: str, term: str, phonetic: str | None, replacement: str | None
    ) -> PronunciationEntryRecord:
        with self.database.session() as s:
            record = PronunciationEntryRecord(
                id=f"pron_{uuid4().hex[:16]}",
                project_id=project_id,
                term=term,
                phonetic=phonetic,
                replacement_text=replacement,
            )
            s.add(record)
            s.commit()
            return record


class ProductionSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, project_id: str) -> ProjectProductionSettingsRecord:
        with self.database.session() as session:
            record = session.get(ProjectProductionSettingsRecord, project_id)
            if record:
                return record
            record = ProjectProductionSettingsRecord(
                project_id=project_id, narrator_voice_profile_id=None, default_direction_json=None
            )
            session.add(record)
            session.commit()
            return record

    def update(
        self, project_id: str, narrator_voice_profile_id: str | None, default_direction_json: str | None
    ) -> ProjectProductionSettingsRecord:
        with self.database.session() as session:
            record = session.get(ProjectProductionSettingsRecord, project_id)
            if not record:
                record = ProjectProductionSettingsRecord(project_id=project_id)
                session.add(record)
            record.narrator_voice_profile_id = narrator_voice_profile_id
            record.default_direction_json = default_direction_json
            session.commit()
            return record

    def override(self, segment_id: str) -> SegmentProductionOverrideRecord | None:
        with self.database.session() as session:
            return session.get(SegmentProductionOverrideRecord, segment_id)

    def overrides(self, segment_ids: list[str]) -> dict[str, SegmentProductionOverrideRecord]:
        if not segment_ids:
            return {}
        with self.database.session() as session:
            rows = session.scalars(
                select(SegmentProductionOverrideRecord).where(
                    SegmentProductionOverrideRecord.segment_id.in_(segment_ids)
                )
            )
            return {row.segment_id: row for row in rows}

    def update_override(
        self, segment_id: str, voice_profile_id: str | None, direction_json: str | None
    ) -> SegmentProductionOverrideRecord:
        with self.database.session() as session:
            record = session.get(SegmentProductionOverrideRecord, segment_id)
            if not record:
                record = SegmentProductionOverrideRecord(segment_id=segment_id)
                session.add(record)
            record.voice_profile_id = voice_profile_id
            record.direction_json = direction_json
            session.commit()
            return record
