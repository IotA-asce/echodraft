from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from echodraft_domain import (
    DirectionProfile,
    Job,
    JobState,
    ParserWarning,
    Project,
    ProjectCreate,
    RenderQueueItem,
    RightsStatus,
    SourceDocument,
    SegmentDirection,
    SpeakerAttribution,
    StructureParserWarning,
)
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .database import Database
from .models import (
    CastGraphDecisionRecord,
    CastMergeDecisionRecord,
    CastingDecisionRecord,
    ChapterRecord,
    CharacterMentionRecord,
    CharacterRecord,
    CharacterVoiceAssignmentRecord,
    CommentRecord,
    IssueRecord,
    InferenceCacheRecord,
    JobCheckpointRecord,
    JobEventRecord,
    JobRecord,
    PatchAttemptRecord,
    ProjectProductionSettingsRecord,
    PronunciationEntryRecord,
    ProjectRecord,
    RenderQueueItemRecord,
    RightsDeclarationRecord,
    SceneRecord,
    SegmentDirectionRecord,
    SegmentRecord,
    SegmentRenderRecord,
    SpeakerAttributionRecord,
    StructureLockRecord,
    StructureParserWarningRecord,
    SegmentRevisionRecord,
    SegmentProductionOverrideRecord,
    SourceDocumentRecord,
    VoiceProfileRecord,
)


def _delete_segment_dependents(session: Session, segment_ids: list[str]) -> None:
    """Remove every row that references the given segments before the segments are deleted.

    Foreign keys are enforced (PRAGMA foreign_keys=ON), so a wholesale structure replace
    must delete dependents first. Ordered children-before-parents: patch attempts and
    comments reference issues and renders, which in turn reference the segment.
    """
    if not segment_ids:
        return
    issue_ids = list(
        session.scalars(select(IssueRecord.id).where(IssueRecord.segment_id.in_(segment_ids)))
    )
    session.execute(
        delete(PatchAttemptRecord).where(PatchAttemptRecord.segment_id.in_(segment_ids))
    )
    if issue_ids:
        session.execute(delete(CommentRecord).where(CommentRecord.issue_id.in_(issue_ids)))
        session.execute(delete(IssueRecord).where(IssueRecord.id.in_(issue_ids)))
    session.execute(
        delete(RenderQueueItemRecord).where(RenderQueueItemRecord.segment_id.in_(segment_ids))
    )
    session.execute(
        delete(SegmentRenderRecord).where(SegmentRenderRecord.segment_id.in_(segment_ids))
    )
    session.execute(
        delete(SegmentProductionOverrideRecord).where(
            SegmentProductionOverrideRecord.segment_id.in_(segment_ids)
        )
    )
    session.execute(
        delete(SegmentDirectionRecord).where(SegmentDirectionRecord.segment_id.in_(segment_ids))
    )
    session.execute(
        delete(SpeakerAttributionRecord).where(
            SpeakerAttributionRecord.segment_id.in_(segment_ids)
        )
    )
    session.execute(
        delete(SegmentRevisionRecord).where(SegmentRevisionRecord.segment_id.in_(segment_ids))
    )


def _structure_warning(record: StructureParserWarningRecord) -> StructureParserWarning:
    return StructureParserWarning.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "sourceDocumentId": record.source_document_id,
            "scopeType": record.scope_type,
            "scopeId": record.scope_id,
            "severity": record.severity,
            "message": record.message,
            "evidence": json.loads(record.evidence_json),
            "confidence": record.confidence,
            "resolved": record.resolved,
            "createdAt": record.created_at,
        }
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


def _speaker_attribution(
    record: SpeakerAttributionRecord, voice_profile_id: str | None = None
) -> SpeakerAttribution:
    return SpeakerAttribution.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "segmentId": record.segment_id,
            "characterId": record.character_id,
            "speakerName": record.speaker_name,
            "method": record.method,
            "evidence": json.loads(record.evidence_json),
            "confidence": record.confidence,
            "status": record.status,
            "userLocked": record.user_locked,
            "autoAccepted": record.auto_accepted,
            "decisionTier": record.decision_tier,
            "reviewTaskId": record.review_task_id,
            "voiceProfileId": voice_profile_id,
            "createdAt": record.created_at,
            "updatedAt": record.updated_at,
        }
    )


def _segment_direction(record: SegmentDirectionRecord) -> SegmentDirection:
    try:
        evidence = json.loads(record.evidence_json)
    except (AttributeError, json.JSONDecodeError):
        evidence = {}
    if not isinstance(evidence, dict):
        evidence = {}
    return SegmentDirection.model_validate(
        {
            "segmentId": record.segment_id,
            "projectId": record.project_id,
            "direction": DirectionProfile.model_validate(json.loads(record.direction_json)),
            "source": record.source,
            "userLocked": record.user_locked,
            "evidence": evidence,
            "directionFingerprint": record.direction_fingerprint,
            "createdAt": record.created_at,
            "updatedAt": record.updated_at,
        }
    )


def _render_queue_item(record: RenderQueueItemRecord) -> RenderQueueItem:
    return RenderQueueItem.model_validate(
        {
            "id": record.id,
            "projectId": record.project_id,
            "chapterId": record.chapter_id,
            "segmentId": record.segment_id,
            "jobId": record.job_id,
            "status": record.status,
            "voiceProfileId": record.voice_profile_id,
            "provider": record.provider,
            "renderKey": record.render_key,
            "errorMessage": record.error_message,
            "createdAt": record.created_at,
            "startedAt": record.started_at,
            "finishedAt": record.finished_at,
        }
    )


def _list_from_json(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_value(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _json_object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_json_object(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _none_if_blank(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _clamped_float(value: object, fallback: float) -> float:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        try:
            numeric = float(value)
        except ValueError:
            numeric = fallback
        return max(0.0, min(1.0, numeric))
    return fallback


def _clean_strings(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            cleaned.append(normalized)
            seen.add(key)
    return cleaned


def _normalized_name_key(value: str | None) -> str:
    """Canonical name key.

    Mirrors ``_name_key`` in cast_discovery.py / speaker_attribution.py so a name
    normalized in the API layer matches the same name looked up here.
    """
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _merge_decision_pair(name_a: str | None, name_b: str | None) -> tuple[str, str] | None:
    """Normalize two names into a lexically sorted pair, or None if degenerate."""
    keys = sorted({_normalized_name_key(name_a), _normalized_name_key(name_b)})
    if len(keys) != 2 or not keys[0] or not keys[1]:
        return None
    return keys[0], keys[1]


def _merge_relationship_rows(
    existing: list[dict[str, object]], updates: list[dict[str, object]]
) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for row in [*existing, *updates]:
        target = _normalized_name_key(str(row.get("target") or ""))
        relation = _normalized_name_key(str(row.get("relation") or ""))
        if not target or not relation:
            continue
        key = (target, relation)
        current = merged.get(key)
        confidence = _clamped_float(row.get("confidence"), 0.0)
        candidate = {
            "target": str(row.get("target") or "").strip(),
            "relation": str(row.get("relation") or "").strip(),
            "confidence": confidence,
        }
        if not current or confidence >= _clamped_float(current.get("confidence"), 0.0):
            merged[key] = candidate
    return list(merged.values())


def _record_cast_merge_decision(
    session: Session,
    *,
    project_id: str,
    name_a: str | None,
    name_b: str | None,
    decision: str,
    reason: str | None,
) -> CastMergeDecisionRecord | None:
    """Upsert a decision for a name pair inside the caller's session.

    The pair is stored once (normalized + sorted); the latest ruling wins so a
    later confirmation overrides an earlier rejection and vice versa.
    """
    pair = _merge_decision_pair(name_a, name_b)
    if not pair:
        return None
    key_a, key_b = pair
    now = datetime.now(UTC)
    record = session.scalar(
        select(CastMergeDecisionRecord).where(
            CastMergeDecisionRecord.project_id == project_id,
            CastMergeDecisionRecord.name_a == key_a,
            CastMergeDecisionRecord.name_b == key_b,
        )
    )
    if record:
        record.decision = decision
        record.reason = reason
        record.created_at = now
        return record
    record = CastMergeDecisionRecord(
        id=f"castmerge_{uuid4().hex[:16]}",
        project_id=project_id,
        name_a=key_a,
        name_b=key_b,
        decision=decision,
        reason=reason,
        created_at=now,
    )
    session.add(record)
    return record


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

    def list_for_project(
        self,
        project_id: str,
        *,
        job_type: str | None = None,
        statuses: list[JobState] | None = None,
        limit: int = 20,
    ) -> list[Job]:
        statement = select(JobRecord).where(JobRecord.project_id == project_id)
        if job_type:
            statement = statement.where(JobRecord.job_type == job_type)
        if statuses:
            statement = statement.where(JobRecord.status.in_([status.value for status in statuses]))
        statement = statement.order_by(JobRecord.created_at.desc()).limit(max(1, min(limit, 100)))
        with self.database.session() as session:
            return [_job(record) for record in session.scalars(statement)]

    def reconcile_interrupted(
        self,
        *,
        resumable_job_types: set[str] | None = None,
        has_checkpoints: Callable[[str], bool] | None = None,
    ) -> list[Job]:
        """Reconcile jobs left ``RUNNING`` by an interrupted process.

        Jobs whose type is in ``resumable_job_types`` and that recorded orchestrator
        checkpoints (as reported by ``has_checkpoints``) are re-queued for resume:
        their status returns to ``QUEUED`` with a ``resumedAt`` note in progress, and
        their timing/error fields are cleared. Every other interrupted job keeps the
        historical fail-closed behaviour. Returns the jobs that were re-queued so the
        caller can re-run them once the job runner is available.
        """
        resumable_types = resumable_job_types or set()
        # Phase 1: read the interrupted job ids (read-only, no open write transaction).
        with self.database.session() as session:
            running = [
                (record.id, record.job_type)
                for record in session.scalars(
                    select(JobRecord).where(JobRecord.status == JobState.RUNNING.value)
                )
            ]
        # Phase 2: decide which ones can resume (may consult other tables/repositories).
        resume_ids = {
            job_id
            for job_id, job_type in running
            if job_type in resumable_types
            and has_checkpoints is not None
            and has_checkpoints(job_id)
        }
        # Phase 3: apply the reconciliation.
        now = datetime.now(UTC)
        resumed: list[Job] = []
        with self.database.session() as session:
            for job_id, _job_type in running:
                record = session.get(JobRecord, job_id)
                if record is None:
                    continue
                if job_id in resume_ids:
                    record.status = JobState.QUEUED.value
                    record.started_at = None
                    record.finished_at = None
                    record.error_message = None
                    record.progress_json = json.dumps(
                        self._resumed_progress(record.progress_json, now)
                    )
                    resumed.append(_job(record))
                else:
                    record.status = JobState.FAILED.value
                    record.error_message = (
                        "interrupted: restart the requested workflow from its last "
                        "persisted artifact"
                    )
                    record.finished_at = now
            session.commit()
        return resumed

    @staticmethod
    def _resumed_progress(progress_json: str | None, now: datetime) -> dict[str, object]:
        base: dict[str, object] = {}
        if progress_json:
            try:
                loaded = json.loads(progress_json)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                base = loaded
        base["resumedAt"] = now.isoformat()
        base["resumeNote"] = (
            "re-enqueued from orchestrator checkpoints after an interrupted run"
        )
        return base

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


class OrchestratorRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_checkpoint(
        self,
        *,
        unit_key: str,
        job_id: str,
        project_id: str | None,
        stage: str,
        stage_version: str,
        scope: dict[str, object],
        status: str,
        output_ref: str | None = None,
        last_error: str | None = None,
    ) -> JobCheckpointRecord:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(JobCheckpointRecord, unit_key)
            if record is None:
                record = JobCheckpointRecord(
                    unit_key=unit_key,
                    job_id=job_id,
                    project_id=project_id,
                    stage=stage,
                    stage_version=stage_version,
                    scope_json=json.dumps(scope, sort_keys=True),
                    status=status,
                    attempt=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.status = status
                record.updated_at = now
                record.scope_json = json.dumps(scope, sort_keys=True)
            if status == "running":
                record.attempt += 1
            record.output_ref = output_ref
            record.last_error = last_error
            session.commit()
            return record

    def checkpoint(self, unit_key: str) -> JobCheckpointRecord | None:
        with self.database.session() as session:
            return session.get(JobCheckpointRecord, unit_key)

    def checkpoints_for_job(
        self, job_id: str, *, stage: str | None = None, status: str | None = None
    ) -> list[JobCheckpointRecord]:
        statement = select(JobCheckpointRecord).where(JobCheckpointRecord.job_id == job_id)
        if stage:
            statement = statement.where(JobCheckpointRecord.stage == stage)
        if status:
            statement = statement.where(JobCheckpointRecord.status == status)
        statement = statement.order_by(JobCheckpointRecord.updated_at.asc())
        with self.database.session() as session:
            return list(session.scalars(statement))

    def put_cache(
        self,
        *,
        cache_key: str,
        kind: str,
        model_id: str,
        model_version: str | None = None,
        schema_id: str | None = None,
        value_json: dict[str, object] | list[object] | None = None,
        value_path: str | None = None,
        size_bytes: int = 0,
    ) -> InferenceCacheRecord:
        if (value_json is None) == (value_path is None):
            raise ValueError("Exactly one of value_json or value_path is required.")
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(InferenceCacheRecord, cache_key)
            payload = json.dumps(value_json, sort_keys=True) if value_json is not None else None
            if record is None:
                record = InferenceCacheRecord(
                    cache_key=cache_key,
                    kind=kind,
                    model_id=model_id,
                    model_version=model_version,
                    schema_id=schema_id,
                    value_json=payload,
                    value_path=value_path,
                    bytes=size_bytes,
                    hit_count=0,
                    created_at=now,
                )
                session.add(record)
            else:
                record.kind = kind
                record.model_id = model_id
                record.model_version = model_version
                record.schema_id = schema_id
                record.value_json = payload
                record.value_path = value_path
                record.bytes = size_bytes
            session.commit()
            return record

    def cache_entry(self, cache_key: str, *, record_hit: bool = False) -> InferenceCacheRecord | None:
        with self.database.session() as session:
            record = session.get(InferenceCacheRecord, cache_key)
            if record and record_hit:
                record.hit_count += 1
                record.last_hit_at = datetime.now(UTC)
                session.commit()
            return record

    def append_event(
        self,
        *,
        job_id: str,
        project_id: str | None,
        event_type: str,
        stage: str | None = None,
        scope: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
    ) -> JobEventRecord:
        record = JobEventRecord(
            job_id=job_id,
            project_id=project_id,
            type=event_type,
            stage=stage,
            scope_json=json.dumps(scope or {}, sort_keys=True),
            payload_json=json.dumps(payload or {}, sort_keys=True),
            ts=datetime.now(UTC),
        )
        with self.database.session() as session:
            session.add(record)
            session.commit()
            return record

    def events_for_job(self, job_id: str, *, after_event_id: int = 0) -> list[JobEventRecord]:
        statement = (
            select(JobEventRecord)
            .where(JobEventRecord.job_id == job_id)
            .where(JobEventRecord.event_id > after_event_id)
            .order_by(JobEventRecord.event_id.asc())
        )
        with self.database.session() as session:
            return list(session.scalars(statement))


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

    def get(self, source_id: str) -> SourceDocument | None:
        with self.database.session() as session:
            record = session.get(SourceDocumentRecord, source_id)
            return self._model(record) if record else None

    def latest(self, project_id: str) -> SourceDocument | None:
        with self.database.session() as session:
            record = session.scalar(
                select(SourceDocumentRecord)
                .where(SourceDocumentRecord.project_id == project_id)
                .order_by(SourceDocumentRecord.imported_at.desc())
            )
            if not record:
                return None
            return self._model(record)

    @staticmethod
    def _model(record: SourceDocumentRecord) -> SourceDocument:
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
                "structureSignalsPath": record.structure_signals_path,
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

    def replace(
        self,
        project_id: str,
        hierarchy: list[dict[str, Any]],
        warnings: list[dict[str, Any]] | None = None,
    ) -> None:
        with self.database.session() as session:
            new_segment_ids = {
                str(segment["id"])
                for chapter in hierarchy
                for scene in chapter["scenes"]
                for segment in scene["segments"]
            }
            old_chapter_ids = list(
                session.scalars(select(ChapterRecord.id).where(ChapterRecord.project_id == project_id))
            )
            old_scene_ids = list(
                session.scalars(
                    select(SceneRecord.id).where(SceneRecord.chapter_id.in_(old_chapter_ids))
                )
            ) if old_chapter_ids else []
            locked_segments = list(
                session.scalars(
                    select(SegmentRecord).where(
                        SegmentRecord.scene_id.in_(old_scene_ids),
                        SegmentRecord.user_locked.is_(True),
                    )
                )
            ) if old_scene_ids else []
            locked_by_id = {segment.id: segment for segment in locked_segments}
            # Unlocked segments are upserted in place when they reappear under the same
            # (deterministic) id and deleted only when genuinely removed. Foreign keys are
            # enforced, so deleting a segment out from under its renders/issues/directions would
            # fail; updating the reused rows in place keeps those references valid.
            unlocked_by_id = {
                segment.id: segment
                for segment in (
                    session.scalars(
                        select(SegmentRecord).where(
                            SegmentRecord.scene_id.in_(old_scene_ids),
                            SegmentRecord.user_locked.is_(False),
                        )
                    )
                    if old_scene_ids
                    else []
                )
            }
            session.execute(
                delete(StructureParserWarningRecord).where(
                    StructureParserWarningRecord.project_id == project_id
                )
            )
            session.execute(
                delete(CharacterMentionRecord).where(CharacterMentionRecord.project_id == project_id)
            )
            session.execute(
                delete(CastGraphDecisionRecord).where(
                    CastGraphDecisionRecord.project_id == project_id
                )
            )
            new_chapter_ids = [str(chapter["record"]["id"]) for chapter in hierarchy]
            new_scene_ids = [
                str(scene["record"]["id"])
                for chapter in hierarchy
                for scene in chapter["scenes"]
            ]
            existing_chapters = {
                record.id: record
                for record in session.scalars(
                    select(ChapterRecord).where(ChapterRecord.id.in_(new_chapter_ids))
                )
            } if new_chapter_ids else {}
            existing_scenes = {
                record.id: record
                for record in session.scalars(
                    select(SceneRecord).where(SceneRecord.id.in_(new_scene_ids))
                )
            } if new_scene_ids else {}
            new_scenes: list[dict[str, Any]] = []
            order_counts: dict[str, int] = {}
            placed_locked_segment_ids: set[str] = set()
            for chapter in hierarchy:
                chapter_record = chapter["record"]
                chapter_id = str(chapter_record["id"])
                existing_chapter = existing_chapters.get(chapter_id)
                if existing_chapter:
                    for key, value in chapter_record.items():
                        setattr(existing_chapter, key, value)
                else:
                    session.add(ChapterRecord(**chapter_record))
                for scene in chapter["scenes"]:
                    scene_record = scene["record"]
                    scene_id = str(scene_record["id"])
                    existing_scene = existing_scenes.get(scene_id)
                    if existing_scene:
                        for key, value in scene_record.items():
                            setattr(existing_scene, key, value)
                    else:
                        session.add(SceneRecord(**scene_record))
                    new_scenes.append(scene_record)
                    order_counts[scene_id] = 0
                    for segment in scene["segments"]:
                        segment_id = str(segment["id"])
                        locked_segment = locked_by_id.get(segment_id)
                        existing_unlocked = unlocked_by_id.get(segment_id)
                        if locked_segment:
                            locked_segment.scene_id = scene_id
                            locked_segment.order_index = order_counts[scene_id]
                            placed_locked_segment_ids.add(segment_id)
                        elif existing_unlocked:
                            for key, value in segment.items():
                                setattr(existing_unlocked, key, value)
                        else:
                            session.add(SegmentRecord(**segment))
                        order_counts[scene_id] += 1
            for segment in locked_segments:
                if segment.id in placed_locked_segment_ids:
                    continue
                target_scene = next(
                    (
                        scene
                        for scene in new_scenes
                        if scene["start_offset"] <= segment.start_offset <= scene["end_offset"]
                    ),
                    new_scenes[0] if new_scenes else None,
                )
                if target_scene:
                    target_scene_id = str(target_scene["id"])
                    segment.scene_id = target_scene_id
                    segment.order_index = order_counts[target_scene_id]
                    order_counts[target_scene_id] += 1
            removed_segment_ids = [
                segment_id for segment_id in unlocked_by_id if segment_id not in new_segment_ids
            ]
            if removed_segment_ids:
                _delete_segment_dependents(session, removed_segment_ids)
                session.execute(
                    delete(SegmentRecord).where(SegmentRecord.id.in_(removed_segment_ids))
                )
            stale_scene_ids = [scene_id for scene_id in old_scene_ids if scene_id not in new_scene_ids]
            if stale_scene_ids:
                session.execute(delete(SceneRecord).where(SceneRecord.id.in_(stale_scene_ids)))
            stale_chapter_ids = [
                chapter_id for chapter_id in old_chapter_ids if chapter_id not in new_chapter_ids
            ]
            if stale_chapter_ids:
                session.execute(delete(ChapterRecord).where(ChapterRecord.id.in_(stale_chapter_ids)))
            for warning in warnings or []:
                session.add(StructureParserWarningRecord(**warning))
            session.commit()

    def warnings(self, project_id: str) -> list[StructureParserWarning]:
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(StructureParserWarningRecord)
                    .where(StructureParserWarningRecord.project_id == project_id)
                    .order_by(StructureParserWarningRecord.created_at)
                )
            )
        return [_structure_warning(record) for record in records]

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

    def update_chapter(
        self, chapter_id: str, title: str | None = None, status: str | None = None
    ) -> ChapterRecord | None:
        with self.database.session() as session:
            record = session.get(ChapterRecord, chapter_id)
            if not record:
                return None
            if title is not None:
                record.title = title.strip() or None
            if status is not None:
                record.status = status
            session.commit()
            return record

    def scenes(self, chapter_id: str) -> list[SceneRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(SceneRecord)
                    .where(SceneRecord.chapter_id == chapter_id)
                    .order_by(SceneRecord.order_index)
                )
            )

    def scene(self, scene_id: str) -> SceneRecord | None:
        with self.database.session() as session:
            return session.get(SceneRecord, scene_id)

    def update_scene(self, scene_id: str, status: str | None = None) -> SceneRecord | None:
        with self.database.session() as session:
            record = session.get(SceneRecord, scene_id)
            if not record:
                return None
            if status is not None:
                record.status = status
            session.commit()
            return record

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

    def set_lock(
        self, scope_type: str, scope_id: str, locked: bool, reason: str | None
    ) -> ChapterRecord | SceneRecord | SegmentRecord | None:
        with self.database.session() as session:
            target: ChapterRecord | SceneRecord | SegmentRecord | None
            project_id: str | None = None
            if scope_type == "chapter":
                target = session.get(ChapterRecord, scope_id)
                project_id = target.project_id if target else None
            elif scope_type == "scene":
                target = session.get(SceneRecord, scope_id)
                chapter = session.get(ChapterRecord, target.chapter_id) if target else None
                project_id = chapter.project_id if chapter else None
            elif scope_type == "segment":
                target = session.get(SegmentRecord, scope_id)
                scene = session.get(SceneRecord, target.scene_id) if target else None
                chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
                project_id = chapter.project_id if chapter else None
            else:
                return None
            if not target or not project_id:
                return None
            target.user_locked = locked
            target.lock_reason = reason if locked else None
            session.execute(
                delete(StructureLockRecord).where(
                    StructureLockRecord.scope_type == scope_type,
                    StructureLockRecord.scope_id == scope_id,
                )
            )
            if locked:
                session.add(
                    StructureLockRecord(
                        id=f"structlock_{uuid4().hex[:16]}",
                        project_id=project_id,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        reason=reason,
                        created_at=datetime.now(UTC),
                    )
                )
            session.commit()
            return target

    def split_segment(self, segment_id: str, split_offset: int) -> SegmentRecord | None:
        with self.database.session() as session:
            record = session.get(SegmentRecord, segment_id)
            if not record:
                return None
            text = record.text_content
            if record.user_locked or split_offset <= 0 or split_offset >= len(text):
                raise ValueError("Segment cannot be split at that offset.")
            left = text[:split_offset].strip()
            right = text[split_offset:].strip()
            if not left or not right:
                raise ValueError("Split must leave text on both sides.")
            session.add(
                SegmentRevisionRecord(
                    id=f"segrev_{uuid4().hex[:16]}",
                    segment_id=segment_id,
                    revision=record.revision,
                    text_content=record.text_content,
                    created_at=datetime.now(UTC),
                )
            )
            following = list(
                session.scalars(
                    select(SegmentRecord)
                    .where(
                        SegmentRecord.scene_id == record.scene_id,
                        SegmentRecord.order_index > record.order_index,
                    )
                    .order_by(SegmentRecord.order_index.desc())
                )
            )
            for item in following:
                item.order_index += 1
            new_segment = SegmentRecord(
                id=f"seg_{uuid4().hex[:16]}",
                scene_id=record.scene_id,
                order_index=record.order_index + 1,
                text_content=right,
                normalized_text=right,
                segment_type=record.segment_type,
                speaker_candidate=record.speaker_candidate,
                speaker_confidence=record.speaker_confidence,
                start_offset=record.start_offset + split_offset,
                end_offset=record.end_offset,
                revision=1,
                status="needs_review",
                parser_evidence_json=record.parser_evidence_json,
            )
            record.text_content = left
            record.normalized_text = left
            record.end_offset = record.start_offset + split_offset
            record.revision += 1
            record.status = "needs_review"
            session.add(new_segment)
            session.commit()
            return record

    def merge_segments(self, segment_id: str, next_segment_id: str) -> SegmentRecord | None:
        with self.database.session() as session:
            record = session.get(SegmentRecord, segment_id)
            next_record = session.get(SegmentRecord, next_segment_id)
            if not record or not next_record:
                return None
            if (
                record.scene_id != next_record.scene_id
                or next_record.order_index != record.order_index + 1
                or record.user_locked
                or next_record.user_locked
            ):
                raise ValueError("Only adjacent unlocked segments in the same scene can be merged.")
            session.add(
                SegmentRevisionRecord(
                    id=f"segrev_{uuid4().hex[:16]}",
                    segment_id=segment_id,
                    revision=record.revision,
                    text_content=record.text_content,
                    created_at=datetime.now(UTC),
                )
            )
            record.text_content = f"{record.text_content.rstrip()} {next_record.text_content.lstrip()}".strip()
            record.normalized_text = record.text_content
            record.end_offset = next_record.end_offset
            record.revision += 1
            record.status = "needs_review"
            session.execute(
                delete(SegmentRevisionRecord).where(
                    SegmentRevisionRecord.segment_id == next_segment_id
                )
            )
            session.delete(next_record)
            following = list(
                session.scalars(
                    select(SegmentRecord)
                    .where(
                        SegmentRecord.scene_id == record.scene_id,
                        SegmentRecord.order_index > next_record.order_index,
                    )
                    .order_by(SegmentRecord.order_index)
                )
            )
            for item in following:
                item.order_index -= 1
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


class SpeakerAttributionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_attributions(
        self, project_id: str, status: str | None = None
    ) -> list[SpeakerAttribution]:
        with self.database.session() as session:
            statement = select(SpeakerAttributionRecord).where(
                SpeakerAttributionRecord.project_id == project_id
            )
            if status:
                statement = statement.where(SpeakerAttributionRecord.status == status)
            records = list(
                session.scalars(statement.order_by(SpeakerAttributionRecord.updated_at.desc()))
            )
            assignments = self._voice_assignments(session, [record.character_id for record in records])
            return [
                _speaker_attribution(
                    record,
                    assignments.get(record.character_id) if record.character_id else None,
                )
                for record in records
            ]

    def by_segment_ids(self, segment_ids: list[str]) -> dict[str, SpeakerAttributionRecord]:
        if not segment_ids:
            return {}
        with self.database.session() as session:
            rows = session.scalars(
                select(SpeakerAttributionRecord).where(
                    SpeakerAttributionRecord.segment_id.in_(segment_ids)
                )
            )
            return {row.segment_id: row for row in rows}

    def resolved_voice_profiles(self, segment_ids: list[str]) -> dict[str, str]:
        if not segment_ids:
            return {}
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(SpeakerAttributionRecord).where(
                        SpeakerAttributionRecord.segment_id.in_(segment_ids),
                        SpeakerAttributionRecord.status == "approved",
                        SpeakerAttributionRecord.character_id.is_not(None),
                    )
                )
            )
            assignments = self._voice_assignments(session, [row.character_id for row in rows])
            return {
                row.segment_id: assignments[row.character_id]
                for row in rows
                if row.character_id and row.character_id in assignments
            }

    def upsert(
        self,
        project_id: str,
        segment_id: str,
        *,
        character_id: str | None,
        speaker_name: str | None,
        method: str,
        evidence: dict[str, object],
        confidence: float,
        status: str,
    ) -> SpeakerAttribution:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.scalar(
                select(SpeakerAttributionRecord).where(
                    SpeakerAttributionRecord.segment_id == segment_id
                )
            )
            if record and record.user_locked:
                assignment = self._voice_assignments(session, [record.character_id]).get(
                    record.character_id
                ) if record.character_id else None
                return _speaker_attribution(record, assignment)
            if not record:
                record = SpeakerAttributionRecord(
                    id=f"spkattr_{uuid4().hex[:16]}",
                    project_id=project_id,
                    segment_id=segment_id,
                    created_at=now,
                    updated_at=now,
                    character_id=character_id,
                    speaker_name=speaker_name,
                    method=method,
                    evidence_json=json.dumps(evidence),
                    confidence=confidence,
                    status=status,
                    user_locked=False,
                )
                session.add(record)
            else:
                record.character_id = character_id
                record.speaker_name = speaker_name
                record.method = method
                record.evidence_json = json.dumps(evidence)
                record.confidence = confidence
                record.status = status
                record.updated_at = now
            session.commit()
            assignment = self._voice_assignments(session, [record.character_id]).get(
                record.character_id
            ) if record.character_id else None
            return _speaker_attribution(record, assignment)

    def update(
        self,
        attribution_id: str,
        *,
        character_id: str | None,
        update_character: bool,
        speaker_name: str | None,
        status: str | None,
        user_locked: bool | None,
    ) -> SpeakerAttribution | None:
        with self.database.session() as session:
            record = session.get(SpeakerAttributionRecord, attribution_id)
            if not record:
                return None
            if update_character:
                if character_id is None:
                    record.character_id = None
                else:
                    character = session.get(CharacterRecord, character_id)
                    if not character or character.project_id != record.project_id:
                        raise ValueError("Character must belong to the same project.")
                    record.character_id = character_id
            if speaker_name is not None:
                record.speaker_name = speaker_name.strip() or None
            if status is not None:
                record.status = status
            if user_locked is not None:
                record.user_locked = user_locked
            record.updated_at = datetime.now(UTC)
            session.commit()
            assignment = self._voice_assignments(session, [record.character_id]).get(
                record.character_id
            ) if record.character_id else None
            return _speaker_attribution(record, assignment)

    def propagate_confirmation(
        self,
        project_id: str,
        *,
        source_attribution_id: str,
        character_id: str,
        speaker_name: str | None,
    ) -> int:
        """Teach a confirmation to every unresolved sibling with the same speaker.

        Rows are eligible when they share the confirmed row's normalized speaker
        name, are not ``user_locked``, and are either unlinked or still
        pending/needs_review. Locked rows and rows already approved to a different
        character are never touched. Returns how many rows were updated.
        """
        key = _normalized_name_key(speaker_name)
        if not key:
            return 0
        now = datetime.now(UTC)
        with self.database.session() as session:
            rows = session.scalars(
                select(SpeakerAttributionRecord).where(
                    SpeakerAttributionRecord.project_id == project_id,
                    SpeakerAttributionRecord.id != source_attribution_id,
                    SpeakerAttributionRecord.user_locked.is_(False),
                )
            )
            count = 0
            for row in rows:
                if _normalized_name_key(row.speaker_name) != key:
                    continue
                if row.character_id is not None and row.status not in {"pending", "needs_review"}:
                    continue
                evidence = json.loads(row.evidence_json or "{}")
                if not isinstance(evidence, dict):
                    evidence = {}
                evidence["method"] = "propagated_from_confirmation"
                evidence["sourceAttributionId"] = source_attribution_id
                row.character_id = character_id
                row.status = "approved"
                row.confidence = max(row.confidence, 0.9)
                row.evidence_json = json.dumps(evidence)
                row.updated_at = now
                count += 1
            session.commit()
            return count

    def locked_exemplars(
        self, project_id: str, limit: int = 5
    ) -> list[tuple[str, str]]:
        """(speaker_name, segment_text) for approved + user-locked rows.

        These seed few-shot exemplars for the LLM attribution prompt. Ordered by
        most recent decision for deterministic, capped output.
        """
        with self.database.session() as session:
            rows = session.execute(
                select(SpeakerAttributionRecord, SegmentRecord.text_content)
                .join(SegmentRecord, SpeakerAttributionRecord.segment_id == SegmentRecord.id)
                .where(
                    SpeakerAttributionRecord.project_id == project_id,
                    SpeakerAttributionRecord.status == "approved",
                    SpeakerAttributionRecord.user_locked.is_(True),
                    SpeakerAttributionRecord.speaker_name.is_not(None),
                )
                .order_by(
                    SpeakerAttributionRecord.updated_at.desc(),
                    SpeakerAttributionRecord.id.desc(),
                )
            )
            exemplars: list[tuple[str, str]] = []
            for record, text_content in rows:
                if record.speaker_name and text_content:
                    exemplars.append((record.speaker_name, text_content))
                if len(exemplars) >= limit:
                    break
            return exemplars

    def character_segment_texts(self, character_id: str, limit: int = 3) -> list[str]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SegmentRecord.text_content)
                .join(SpeakerAttributionRecord, SpeakerAttributionRecord.segment_id == SegmentRecord.id)
                .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                .where(
                    SpeakerAttributionRecord.character_id == character_id,
                    SpeakerAttributionRecord.status == "approved",
                )
                .order_by(
                    ChapterRecord.order_index,
                    SceneRecord.order_index,
                    SegmentRecord.order_index,
                    SpeakerAttributionRecord.confidence.desc(),
                )
                .limit(limit)
            )
            return [text for text in rows if text]

    @staticmethod
    def _voice_assignments(session: Any, character_ids: list[str | None]) -> dict[str, str]:
        ids = [item for item in character_ids if item]
        if not ids:
            return {}
        rows = session.scalars(
            select(CharacterVoiceAssignmentRecord).where(
                CharacterVoiceAssignmentRecord.character_id.in_(ids)
            )
        )
        return {row.character_id: row.voice_profile_id for row in rows}


class CastMergeDecisionRepository:
    """Persisted human rulings on whether two cast names are the same person."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        project_id: str,
        name_a: str,
        name_b: str,
        decision: str,
        reason: str | None = None,
    ) -> CastMergeDecisionRecord | None:
        with self.database.session() as session:
            record = _record_cast_merge_decision(
                session,
                project_id=project_id,
                name_a=name_a,
                name_b=name_b,
                decision=decision,
                reason=reason,
            )
            session.commit()
            return record

    def decision_for(
        self, project_id: str, name_a: str, name_b: str
    ) -> CastMergeDecisionRecord | None:
        pair = _merge_decision_pair(name_a, name_b)
        if not pair:
            return None
        key_a, key_b = pair
        with self.database.session() as session:
            return session.scalar(
                select(CastMergeDecisionRecord).where(
                    CastMergeDecisionRecord.project_id == project_id,
                    CastMergeDecisionRecord.name_a == key_a,
                    CastMergeDecisionRecord.name_b == key_b,
                )
            )

    def is_rejected(self, project_id: str, name_a: str, name_b: str) -> bool:
        decision = self.decision_for(project_id, name_a, name_b)
        return bool(decision and decision.decision == "rejected")

    def recent(self, project_id: str, limit: int = 10) -> list[CastMergeDecisionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CastMergeDecisionRecord)
                    .where(CastMergeDecisionRecord.project_id == project_id)
                    .order_by(
                        CastMergeDecisionRecord.created_at.desc(),
                        CastMergeDecisionRecord.id.desc(),
                    )
                    .limit(limit)
                )
            )


class CastGraphRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def replace_mentions(self, project_id: str, mentions: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            session.execute(
                delete(CharacterMentionRecord).where(
                    CharacterMentionRecord.project_id == project_id
                )
            )
            for mention in mentions:
                session.add(self._mention_record(project_id, mention, now))
            session.commit()

    def record_mention(self, project_id: str, mention: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            session.add(self._mention_record(project_id, mention, now))
            session.commit()

    def replace_decisions(self, project_id: str, decisions: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            session.execute(
                delete(CastGraphDecisionRecord).where(
                    CastGraphDecisionRecord.project_id == project_id
                )
            )
            for decision in decisions:
                session.add(self._decision_record(project_id, decision, now))
            session.commit()

    def record_decision(self, project_id: str, decision: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        with self.database.session() as session:
            session.add(self._decision_record(project_id, decision, now))
            session.commit()

    def mentions(self, project_id: str) -> list[CharacterMentionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CharacterMentionRecord)
                    .where(CharacterMentionRecord.project_id == project_id)
                    .order_by(CharacterMentionRecord.created_at, CharacterMentionRecord.id)
                )
            )

    def decisions(self, project_id: str) -> list[CastGraphDecisionRecord]:
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(CastGraphDecisionRecord)
                    .where(CastGraphDecisionRecord.project_id == project_id)
                    .order_by(CastGraphDecisionRecord.created_at, CastGraphDecisionRecord.id)
                )
            )

    @staticmethod
    def _mention_record(
        project_id: str, mention: dict[str, Any], created_at: datetime
    ) -> CharacterMentionRecord:
        return CharacterMentionRecord(
            id=str(mention.get("id") or f"mention_{uuid4().hex[:16]}"),
            project_id=project_id,
            source_document_id=_none_if_blank(mention.get("sourceDocumentId")),
            scene_id=_none_if_blank(mention.get("sceneId")),
            window_id=str(mention.get("windowId") or ""),
            surface_name=str(mention.get("surfaceName") or ""),
            canonical_guess=_none_if_blank(mention.get("canonicalGuess")),
            normalized_key=str(mention.get("normalizedKey") or ""),
            entity_type=str(mention.get("entityType") or "unknown"),
            role_in_scene=str(mention.get("roleInScene") or "unknown"),
            evidence_text=str(mention.get("evidenceText") or ""),
            segment_ids_json=json.dumps(_string_list(mention.get("segmentIds"))),
            atom_ids_json=json.dumps(_string_list(mention.get("atomIds"))),
            confidence=_clamped_float(mention.get("confidence"), 0.0),
            traits_json=json.dumps(_string_list(mention.get("traitsObserved"))),
            relationships_json=json.dumps(_json_object_list(mention.get("relationshipsObserved"))),
            llm_run_id=_none_if_blank(mention.get("llmRunId")),
            metadata_json=json.dumps(_json_object(mention.get("metadata")), sort_keys=True),
            created_at=created_at,
        )

    @staticmethod
    def _decision_record(
        project_id: str, decision: dict[str, Any], created_at: datetime
    ) -> CastGraphDecisionRecord:
        return CastGraphDecisionRecord(
            id=str(decision.get("id") or f"castdec_{uuid4().hex[:16]}"),
            project_id=project_id,
            source_key=str(decision.get("sourceKey") or ""),
            source_name=str(decision.get("sourceName") or ""),
            decision=str(decision.get("decision") or "unsure"),
            target_character_id=_none_if_blank(decision.get("targetCharacterId")),
            target_name=_none_if_blank(decision.get("targetName")),
            confidence=_clamped_float(decision.get("confidence"), 0.0),
            reason=str(decision.get("reason") or ""),
            evidence_segment_ids_json=json.dumps(_string_list(decision.get("evidenceSegmentIds"))),
            llm_run_id=_none_if_blank(decision.get("llmRunId")),
            metadata_json=json.dumps(_json_object(decision.get("metadata")), sort_keys=True),
            created_at=created_at,
        )


class CastingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def characters(self, project_id: str) -> list[CharacterRecord]:
        with self.database.session() as s:
            return list(
                s.scalars(
                    select(CharacterRecord)
                    .where(CharacterRecord.project_id == project_id)
                    .order_by(CharacterRecord.display_name)
                )
            )

    def character(self, character_id: str) -> CharacterRecord | None:
        with self.database.session() as s:
            return s.get(CharacterRecord, character_id)

    def character_voice_assignments(self, project_id: str) -> dict[str, str]:
        with self.database.session() as s:
            rows = s.scalars(
                select(CharacterVoiceAssignmentRecord).join(
                    CharacterRecord,
                    CharacterVoiceAssignmentRecord.character_id == CharacterRecord.id,
                )
                .where(CharacterRecord.project_id == project_id)
            )
            return {row.character_id: row.voice_profile_id for row in rows}

    def character_voice_assignment(self, character_id: str) -> str | None:
        with self.database.session() as s:
            row = s.scalar(
                select(CharacterVoiceAssignmentRecord).where(
                    CharacterVoiceAssignmentRecord.character_id == character_id
                )
            )
            return row.voice_profile_id if row else None

    def create_character(
        self,
        project_id: str,
        name: str,
        aliases: list[str],
        role: str,
        confidence: float,
        notes: str | None,
        canonical_name: str | None = None,
        traits: list[str] | None = None,
        relationships: list[dict[str, object]] | None = None,
        speaking_style: list[str] | None = None,
        first_seen_source_id: str | None = None,
        first_seen_chapter_id: str | None = None,
        first_seen_segment_id: str | None = None,
    ) -> CharacterRecord:
        with self.database.session() as s:
            clean_name = name.strip()
            record = CharacterRecord(
                id=f"char_{uuid4().hex[:16]}",
                project_id=project_id,
                display_name=clean_name,
                canonical_name=(canonical_name or clean_name).strip(),
                aliases_json=json.dumps(_clean_strings(aliases)),
                traits_json=json.dumps(_clean_strings(traits or [])),
                relationships_json=json.dumps(_json_object_list(relationships)),
                speaking_style_json=json.dumps(_clean_strings(speaking_style or [])),
                first_seen_source_id=first_seen_source_id,
                first_seen_chapter_id=first_seen_chapter_id,
                first_seen_segment_id=first_seen_segment_id,
                merge_history_json="[]",
                split_history_json="[]",
                user_locked=False,
                role_type=role,
                confidence=confidence,
                notes=notes,
            )
            s.add(record)
            s.commit()
            return record

    def update_character(
        self,
        character_id: str,
        *,
        display_name: str | None = None,
        canonical_name: str | None = None,
        aliases: list[str] | None = None,
        traits: list[str] | None = None,
        relationships: list[dict[str, object]] | None = None,
        speaking_style: list[str] | None = None,
        role_type: str | None = None,
        confidence: float | None = None,
        notes: str | None = None,
        user_locked: bool | None = None,
        lock_reason: str | None = None,
        voice_profile_id: str | None = None,
        update_voice: bool = False,
    ) -> CharacterRecord | None:
        with self.database.session() as s:
            record = s.get(CharacterRecord, character_id)
            if not record:
                return None
            if display_name is not None:
                record.display_name = display_name.strip()
            if canonical_name is not None:
                record.canonical_name = canonical_name.strip() or None
            if aliases is not None:
                record.aliases_json = json.dumps(_clean_strings(aliases))
            if traits is not None:
                record.traits_json = json.dumps(_clean_strings(traits))
            if relationships is not None:
                record.relationships_json = json.dumps(_json_object_list(relationships))
            if speaking_style is not None:
                record.speaking_style_json = json.dumps(_clean_strings(speaking_style))
            if role_type is not None:
                record.role_type = role_type
            if confidence is not None:
                record.confidence = confidence
            if notes is not None:
                record.notes = notes
            if user_locked is not None:
                record.user_locked = user_locked
            if lock_reason is not None or user_locked is False:
                record.lock_reason = lock_reason
            if update_voice:
                self._set_assignment(s, record.project_id, record.id, voice_profile_id)
            s.commit()
            return record

    def merge_characters(
        self, target_character_id: str, source_character_id: str, reason: str | None
    ) -> CharacterRecord:
        if target_character_id == source_character_id:
            raise ValueError("Choose two different characters to merge.")
        with self.database.session() as s:
            target = s.get(CharacterRecord, target_character_id)
            source = s.get(CharacterRecord, source_character_id)
            if not target or not source:
                raise KeyError("Character not found")
            if target.project_id != source.project_id:
                raise ValueError("Characters must belong to the same project.")
            if source.merged_into_character_id and source.merged_into_character_id != target.id:
                raise ValueError("Source character was already merged into another character.")
            now = datetime.now(UTC).isoformat()
            target.aliases_json = json.dumps(
                _clean_strings(
                    [
                        *[str(item) for item in _list_from_json(target.aliases_json)],
                        source.display_name,
                        *([source.canonical_name] if source.canonical_name else []),
                        *[str(item) for item in _list_from_json(source.aliases_json)],
                    ]
                )
            )
            target.traits_json = json.dumps(
                _clean_strings(
                    [
                        *[str(item) for item in _list_from_json(target.traits_json)],
                        *[str(item) for item in _list_from_json(source.traits_json)],
                    ]
                )
            )
            target.relationships_json = json.dumps(
                _merge_relationship_rows(
                    _json_object_list(_json_value(target.relationships_json)),
                    _json_object_list(_json_value(source.relationships_json)),
                )
            )
            target.speaking_style_json = json.dumps(
                _clean_strings(
                    [
                        *[str(item) for item in _list_from_json(target.speaking_style_json)],
                        *[str(item) for item in _list_from_json(source.speaking_style_json)],
                    ]
                )
            )
            history = _list_from_json(target.merge_history_json)
            history.append(
                {
                    "sourceCharacterId": source.id,
                    "sourceDisplayName": source.display_name,
                    "reason": reason,
                    "mergedAt": now,
                }
            )
            target.merge_history_json = json.dumps(history)
            source.merged_into_character_id = target.id
            source.user_locked = True
            source.lock_reason = reason or f"Merged into {target.display_name}."
            self._transfer_or_clear_assignment(s, source.id, target.id)
            # Re-point the merged-away character's speaker attributions to the
            # surviving record so every confirmed line follows the merge.
            s.execute(
                update(SpeakerAttributionRecord)
                .where(SpeakerAttributionRecord.character_id == source.id)
                .values(character_id=target.id)
            )
            _record_cast_merge_decision(
                s,
                project_id=target.project_id,
                name_a=target.display_name,
                name_b=source.display_name,
                decision="confirmed",
                reason=reason,
            )
            s.commit()
            return target

    def split_character(
        self,
        character_id: str,
        display_name: str,
        aliases: list[str],
        traits: list[str],
        reason: str | None,
    ) -> CharacterRecord:
        with self.database.session() as s:
            source = s.get(CharacterRecord, character_id)
            if not source:
                raise KeyError(character_id)
            now = datetime.now(UTC).isoformat()
            clean_name = display_name.strip()
            record = CharacterRecord(
                id=f"char_{uuid4().hex[:16]}",
                project_id=source.project_id,
                display_name=clean_name,
                canonical_name=clean_name,
                aliases_json=json.dumps(_clean_strings(aliases)),
                traits_json=json.dumps(_clean_strings(traits)),
                relationships_json="[]",
                speaking_style_json="[]",
                first_seen_source_id=source.first_seen_source_id,
                first_seen_chapter_id=source.first_seen_chapter_id,
                first_seen_segment_id=source.first_seen_segment_id,
                merge_history_json="[]",
                split_history_json=json.dumps(
                    [
                        {
                            "sourceCharacterId": source.id,
                            "sourceDisplayName": source.display_name,
                            "reason": reason,
                            "splitAt": now,
                        }
                    ]
                ),
                user_locked=False,
                role_type=source.role_type,
                confidence=min(source.confidence, 0.75),
                notes=f"Split from {source.display_name}." if not reason else reason,
            )
            source_history = _list_from_json(source.split_history_json)
            source_history.append(
                {
                    "newCharacterId": record.id,
                    "newDisplayName": record.display_name,
                    "reason": reason,
                    "splitAt": now,
                }
            )
            source.split_history_json = json.dumps(source_history)
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

    def assign(
        self,
        character_id: str,
        voice_id: str,
        *,
        user_locked: bool = True,
        locked_reason: str | None = None,
        casting_decision_id: str | None = None,
    ) -> None:
        with self.database.session() as s:
            character = s.get(CharacterRecord, character_id)
            if not character:
                raise KeyError(character_id)
            self._set_assignment(
                s,
                character.project_id,
                character_id,
                voice_id,
                user_locked=user_locked,
                locked_reason=locked_reason,
                casting_decision_id=casting_decision_id,
            )
            s.commit()

    def prepare_automatic_casting_assignments(
        self, project_id: str
    ) -> list[CharacterVoiceAssignmentRecord]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(CharacterVoiceAssignmentRecord)
                    .join(
                        CharacterRecord,
                        CharacterVoiceAssignmentRecord.character_id == CharacterRecord.id,
                    )
                    .where(CharacterRecord.project_id == project_id)
                )
            )
            for row in rows:
                if row.casting_decision_id:
                    continue
                decision = session.scalar(
                    select(CastingDecisionRecord).where(
                        CastingDecisionRecord.character_id == row.character_id,
                        CastingDecisionRecord.role == "character",
                        CastingDecisionRecord.superseded_by_id.is_(None),
                    )
                )
                if decision:
                    row.casting_decision_id = decision.id
                    row.user_locked = decision.user_locked
                    row.locked_reason = decision.locked_reason
                else:
                    row.user_locked = True
                    row.locked_reason = (
                        row.locked_reason
                        or "Legacy hand assignment preserved during automatic casting."
                    )
            session.commit()
            return rows

    def _set_assignment(
        self,
        session: Any,
        project_id: str,
        character_id: str,
        voice_profile_id: str | None,
        *,
        user_locked: bool | None = None,
        locked_reason: str | None = None,
        casting_decision_id: str | None = None,
    ) -> None:
        existing = session.scalar(
            select(CharacterVoiceAssignmentRecord).where(
                CharacterVoiceAssignmentRecord.character_id == character_id
            )
        )
        if voice_profile_id is None:
            if existing:
                session.delete(existing)
            return
        voice = session.get(VoiceProfileRecord, voice_profile_id)
        if not voice or voice.project_id != project_id:
            raise ValueError("Voice profile must belong to the same project.")
        if existing:
            existing.voice_profile_id = voice_profile_id
            if user_locked is None:
                existing.user_locked = True
                existing.locked_reason = "Manual voice assignment preserved."
            else:
                existing.user_locked = user_locked
                existing.locked_reason = locked_reason if user_locked else None
            existing.casting_decision_id = casting_decision_id
        else:
            session.add(
                CharacterVoiceAssignmentRecord(
                    id=f"assign_{uuid4().hex[:16]}",
                    character_id=character_id,
                    voice_profile_id=voice_profile_id,
                    user_locked=user_locked if user_locked is not None else True,
                    locked_reason=(
                        locked_reason
                        if user_locked is not None
                        else "Manual voice assignment preserved."
                    ),
                    casting_decision_id=casting_decision_id,
                )
            )

    def _transfer_or_clear_assignment(
        self, session: Any, source_character_id: str, target_character_id: str
    ) -> None:
        source_assignment = session.scalar(
            select(CharacterVoiceAssignmentRecord).where(
                CharacterVoiceAssignmentRecord.character_id == source_character_id
            )
        )
        if not source_assignment:
            return
        target_assignment = session.scalar(
            select(CharacterVoiceAssignmentRecord).where(
                CharacterVoiceAssignmentRecord.character_id == target_character_id
            )
        )
        if target_assignment:
            session.delete(source_assignment)
        else:
            source_assignment.character_id = target_character_id

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
                project_id=project_id,
                narrator_voice_profile_id=None,
                narrator_casting_decision_id=None,
                casting_style_preset="warm_neutral",
                auto_cast_enabled=True,
                default_direction_json=None,
                auto_sound_design_json=None,
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
                record = ProjectProductionSettingsRecord(
                    project_id=project_id,
                    casting_style_preset="warm_neutral",
                    auto_cast_enabled=True,
                )
                session.add(record)
            record.narrator_voice_profile_id = narrator_voice_profile_id
            record.default_direction_json = default_direction_json
            session.commit()
            return record

    def configure_casting(
        self,
        project_id: str,
        *,
        style_preset: str | None = None,
        auto_cast_enabled: bool | None = None,
        narrator_casting_decision_id: str | None = None,
        update_narrator_decision: bool = False,
    ) -> ProjectProductionSettingsRecord:
        with self.database.session() as session:
            record = session.get(ProjectProductionSettingsRecord, project_id)
            if not record:
                record = ProjectProductionSettingsRecord(
                    project_id=project_id,
                    casting_style_preset="warm_neutral",
                    auto_cast_enabled=True,
                )
                session.add(record)
            if style_preset is not None:
                record.casting_style_preset = style_preset
            if auto_cast_enabled is not None:
                record.auto_cast_enabled = auto_cast_enabled
            if update_narrator_decision:
                record.narrator_casting_decision_id = narrator_casting_decision_id
            session.commit()
            return record

    def configure_sound_design(
        self, project_id: str, auto_sound_design_json: str | None
    ) -> ProjectProductionSettingsRecord:
        with self.database.session() as session:
            record = session.get(ProjectProductionSettingsRecord, project_id)
            if not record:
                record = ProjectProductionSettingsRecord(
                    project_id=project_id,
                    casting_style_preset="warm_neutral",
                    auto_cast_enabled=True,
                )
                session.add(record)
            record.auto_sound_design_json = auto_sound_design_json
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


class SegmentDirectionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def all_for_project(self, project_id: str) -> list[SegmentDirection]:
        with self.database.session() as session:
            records = session.scalars(
                select(SegmentDirectionRecord)
                .where(SegmentDirectionRecord.project_id == project_id)
                .order_by(SegmentDirectionRecord.updated_at.desc())
            )
            return [_segment_direction(record) for record in records]

    def get(self, segment_id: str) -> SegmentDirection | None:
        with self.database.session() as session:
            record = session.get(SegmentDirectionRecord, segment_id)
            return _segment_direction(record) if record else None

    def records(self, segment_ids: list[str]) -> dict[str, SegmentDirectionRecord]:
        if not segment_ids:
            return {}
        with self.database.session() as session:
            rows = session.scalars(
                select(SegmentDirectionRecord).where(
                    SegmentDirectionRecord.segment_id.in_(segment_ids)
                )
            )
            return {row.segment_id: row for row in rows}

    def upsert(
        self,
        project_id: str,
        segment_id: str,
        direction_json: str,
        source: str,
        user_locked: bool,
        direction_fingerprint: str,
        evidence_json: str = "{}",
    ) -> SegmentDirection:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = session.get(SegmentDirectionRecord, segment_id)
            if record and record.user_locked and source in {"inferred", "llm_inferred"}:
                return _segment_direction(record)
            if not record:
                record = SegmentDirectionRecord(
                    segment_id=segment_id,
                    project_id=project_id,
                    direction_json=direction_json,
                    source=source,
                    user_locked=user_locked,
                    evidence_json=evidence_json,
                    direction_fingerprint=direction_fingerprint,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.project_id = project_id
                record.direction_json = direction_json
                record.source = source
                record.user_locked = user_locked
                record.evidence_json = evidence_json
                record.direction_fingerprint = direction_fingerprint
                record.updated_at = now
            session.commit()
            return _segment_direction(record)


class RenderQueueRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_for_project(self, project_id: str, chapter_id: str | None = None) -> list[RenderQueueItem]:
        with self.database.session() as session:
            query = select(RenderQueueItemRecord).where(RenderQueueItemRecord.project_id == project_id)
            if chapter_id:
                query = query.where(RenderQueueItemRecord.chapter_id == chapter_id)
            rows = session.scalars(query.order_by(RenderQueueItemRecord.created_at.desc()))
            return [_render_queue_item(row) for row in rows]

    def enqueue(
        self,
        project_id: str,
        chapter_id: str,
        segment_id: str,
        job_id: str,
        voice_profile_id: str | None,
        provider: str,
    ) -> RenderQueueItem:
        now = datetime.now(UTC)
        with self.database.session() as session:
            record = RenderQueueItemRecord(
                id=f"rq_{uuid4().hex[:16]}",
                project_id=project_id,
                chapter_id=chapter_id,
                segment_id=segment_id,
                job_id=job_id,
                status="queued",
                voice_profile_id=voice_profile_id,
                provider=provider,
                render_key=None,
                error_message=None,
                created_at=now,
                started_at=None,
                finished_at=None,
            )
            session.add(record)
            session.commit()
            return _render_queue_item(record)

    def mark_running(self, item_id: str) -> None:
        with self.database.session() as session:
            record = session.get(RenderQueueItemRecord, item_id)
            if not record:
                return
            record.status = "running"
            record.started_at = datetime.now(UTC)
            session.commit()

    def mark_succeeded(self, item_id: str, render_key: str) -> None:
        with self.database.session() as session:
            record = session.get(RenderQueueItemRecord, item_id)
            if not record:
                return
            record.status = "succeeded"
            record.render_key = render_key
            record.finished_at = datetime.now(UTC)
            session.commit()

    def mark_failed(self, item_id: str, error_message: str) -> None:
        with self.database.session() as session:
            record = session.get(RenderQueueItemRecord, item_id)
            if not record:
                return
            record.status = "failed"
            record.error_message = error_message
            record.finished_at = datetime.now(UTC)
            session.commit()
