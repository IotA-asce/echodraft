from __future__ import annotations

import json
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from echodraft_db.models import (
    ChapterRecord,
    ChapterRenderRecord,
    CharacterRecord,
    CharacterVoiceAssignmentRecord,
    IssueRecord,
    ProjectProductionSettingsRecord,
    ReadinessReportRecord,
    SceneRecord,
    SegmentDirectionRecord,
    SegmentRecord,
    SegmentRenderRecord,
    SourceDocumentRecord,
    SpeakerAttributionRecord,
    StructureParserWarningRecord,
    TextCleanlinessIssueRecord,
    VoiceProfileRecord,
)
from echodraft_domain import ReadinessCheck, ReadinessReport
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .container import AppContainer
from .production import ProductionService


@dataclass(frozen=True)
class CheckDraft:
    id: str
    scope: str
    status: str
    severity: str
    category: str
    title: str
    description: str
    chapter_id: str | None = None
    segment_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class ReadinessService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def run(self, project_id: str, chapter_id: str | None = None) -> ReadinessReport:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        with self.container.structure.database.session() as session:
            if chapter_id:
                chapter = session.get(ChapterRecord, chapter_id)
                if not chapter or chapter.project_id != project_id:
                    raise ValueError("Chapter or project not found.")
            drafts = self._collect_checks(session, project_id, chapter_id)

        checks: list[ReadinessCheck] = []
        for draft in drafts:
            issue_id = None
            resolution_status = None
            if draft.status != "passed":
                issue = self.container.review.create_issue(
                    project_id=project_id,
                    chapter_id=draft.chapter_id,
                    segment_id=draft.segment_id,
                    category=draft.category,
                    severity=draft.severity,
                    title=draft.title,
                    description=draft.description,
                    metadata={**draft.metadata, "readinessCheckId": draft.id},
                    dedupe_key=f"readiness:{project_id}:{chapter_id or 'project'}:{draft.id}",
                )
                issue_id = issue.id
                resolution_status = issue.status
            checks.append(
                ReadinessCheck(
                    id=draft.id,
                    scope=draft.scope,
                    status=draft.status,
                    severity=draft.severity,
                    category=draft.category,
                    title=draft.title,
                    description=draft.description,
                    issueId=issue_id,
                    resolutionStatus=resolution_status,
                    metadata=draft.metadata,
                )
            )

        report = self._store_report(project_id, chapter_id, checks)
        return report

    def latest(self, project_id: str, chapter_id: str | None = None) -> ReadinessReport | None:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        with self.container.structure.database.session() as session:
            query = select(ReadinessReportRecord).where(
                ReadinessReportRecord.project_id == project_id
            )
            if chapter_id:
                query = query.where(ReadinessReportRecord.chapter_id == chapter_id)
            else:
                query = query.where(ReadinessReportRecord.chapter_id.is_(None))
            record = session.scalar(
                query.order_by(ReadinessReportRecord.created_at.desc(), ReadinessReportRecord.id.desc())
            )
            return self._model(record) if record else None

    def reports(self, project_id: str) -> list[ReadinessReport]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        with self.container.structure.database.session() as session:
            records = list(
                session.scalars(
                    select(ReadinessReportRecord)
                    .where(ReadinessReportRecord.project_id == project_id)
                    .order_by(ReadinessReportRecord.created_at.desc())
                )
            )
            return [self._model(record) for record in records]

    def _collect_checks(
        self, session: Session, project_id: str, chapter_id: str | None
    ) -> list[CheckDraft]:
        checks: list[CheckDraft] = []
        chapters = self._chapters(session, project_id, chapter_id)
        segments = self._segments(session, [chapter.id for chapter in chapters])
        segment_ids = [segment.id for segment in segments]
        source_ids = list(
            session.scalars(
                select(SourceDocumentRecord.id).where(SourceDocumentRecord.project_id == project_id)
            )
        )

        if source_ids:
            checks.append(self._passed("text_source", "text", "Canonical source exists."))
            open_cleaning = self._count(
                session,
                select(func.count())
                .select_from(TextCleanlinessIssueRecord)
                .where(
                    TextCleanlinessIssueRecord.source_document_id.in_(source_ids),
                    TextCleanlinessIssueRecord.status == "open",
                ),
            )
            if open_cleaning:
                checks.append(
                    self._issue(
                        "text_cleaning_open",
                        "text",
                        "warning",
                        "readiness_text",
                        "Open Clean Text Review issues",
                        f"{open_cleaning} clean-text issues are still open.",
                        {"openCleaningIssues": open_cleaning},
                    )
                )
            else:
                checks.append(self._passed("text_cleaning", "text", "Clean text review has no open issues."))
        else:
            checks.append(
                self._issue(
                    "text_source_missing",
                    "text",
                    "blocking",
                    "readiness_text",
                    "No imported source",
                    "Import a rights-cleared manuscript before readiness review.",
                )
            )

        if not chapters:
            checks.append(
                self._issue(
                    "structure_missing",
                    "structure",
                    "blocking",
                    "readiness_structure",
                    "No chapter structure",
                    "Extract structure before production readiness can pass.",
                )
            )
            return checks
        checks.append(self._passed("structure_chapters", "structure", f"{len(chapters)} chapters found."))
        if not segments:
            checks.append(
                self._issue(
                    "structure_segments_missing",
                    "structure",
                    "blocking",
                    "readiness_structure",
                    "No renderable segments",
                    "Chapters need scenes and segments before production.",
                    chapter_id=chapter_id,
                )
            )
        else:
            empty_segments = [segment.id for segment in segments if not segment.normalized_text.strip()]
            if empty_segments:
                checks.append(
                    self._issue(
                        "structure_empty_segments",
                        "structure",
                        "warning",
                        "readiness_structure",
                        "Empty segments",
                        f"{len(empty_segments)} segments have no renderable text.",
                        chapter_id=chapter_id,
                        metadata={"segmentIds": empty_segments[:20]},
                    )
                )
            else:
                checks.append(
                    self._passed("structure_segments", "structure", f"{len(segments)} segments are renderable.")
                )

        parser_warnings = self._count(
            session,
            select(func.count()).select_from(StructureParserWarningRecord).where(
                StructureParserWarningRecord.project_id == project_id,
                StructureParserWarningRecord.resolved.is_(False),
            ),
        )
        if parser_warnings:
            checks.append(
                self._issue(
                    "structure_parser_warnings",
                    "structure",
                    "warning",
                    "readiness_structure",
                    "Unresolved parser warnings",
                    f"{parser_warnings} structure parser warnings are unresolved.",
                    metadata={"unresolvedWarnings": parser_warnings},
                )
            )
        else:
            checks.append(self._passed("structure_warnings", "structure", "No unresolved parser warnings."))

        checks.extend(self._speaker_checks(session, project_id, segment_ids, chapter_id))
        checks.extend(self._voice_checks(session, project_id, segment_ids, chapter_id))
        checks.extend(self._direction_checks(session, project_id, segment_ids, chapter_id))
        checks.extend(self._audio_checks(session, project_id, chapters, segments))
        checks.extend(self._export_checks(session, project_id, bool(chapters)))
        return checks

    def _speaker_checks(
        self, session: Session, project_id: str, segment_ids: list[str], chapter_id: str | None
    ) -> list[CheckDraft]:
        if not segment_ids:
            return []
        rows = list(
            session.scalars(
                select(SpeakerAttributionRecord).where(
                    SpeakerAttributionRecord.project_id == project_id,
                    SpeakerAttributionRecord.segment_id.in_(segment_ids),
                )
            )
        )
        review_count = len([row for row in rows if row.status != "approved"])
        if review_count:
            return [
                self._issue(
                    "speaker_review_open",
                    "speaker",
                    "warning",
                    "readiness_speaker",
                    "Speaker review queue is open",
                    f"{review_count} speaker attribution rows still need review.",
                    chapter_id=chapter_id,
                    metadata={"openSpeakerAttributions": review_count, "unresolvedSpeakerRows": review_count},
                )
            ]
        if rows:
            return [self._passed("speaker_attribution", "speaker", "Speaker attributions are approved.")]
        return [
            self._issue(
                "speaker_attribution_missing",
                "speaker",
                "warning",
                "readiness_speaker",
                "Speaker attribution has not run",
                "Run Cast Review before final export readiness.",
                chapter_id=chapter_id,
            )
        ]

    def _voice_checks(
        self, session: Session, project_id: str, segment_ids: list[str], chapter_id: str | None
    ) -> list[CheckDraft]:
        checks: list[CheckDraft] = []
        settings = session.get(ProjectProductionSettingsRecord, project_id)
        if not settings or not settings.narrator_voice_profile_id:
            checks.append(
                self._issue(
                    "voice_narrator_missing",
                    "voice",
                    "blocking",
                    "readiness_voice",
                    "Narrator voice missing",
                    "Choose a narrator voice before readiness can pass.",
                )
            )
        else:
            voice = session.get(VoiceProfileRecord, settings.narrator_voice_profile_id)
            if not voice or voice.project_id != project_id:
                checks.append(
                    self._issue(
                        "voice_narrator_invalid",
                        "voice",
                        "blocking",
                        "readiness_voice",
                        "Narrator voice is invalid",
                        "The selected narrator voice no longer exists in this project.",
                    )
                )
            else:
                checks.append(
                    self._passed(
                        "voice_narrator",
                        "voice",
                        "Narrator voice is configured.",
                    )
                )

        characters = list(
            session.scalars(
                select(CharacterRecord).where(
                    CharacterRecord.project_id == project_id,
                    CharacterRecord.merged_into_character_id.is_(None),
                )
            )
        )
        character_ids = [character.id for character in characters]
        voiced_character_ids = set(
            session.scalars(
                select(CharacterVoiceAssignmentRecord.character_id).where(
                    CharacterVoiceAssignmentRecord.character_id.in_(character_ids)
                )
            )
        ) if character_ids else set()
        unvoiced = [character.id for character in characters if character.id not in voiced_character_ids]
        if characters and unvoiced:
            checks.append(
                self._issue(
                    "voice_character_coverage",
                    "voice",
                    "warning",
                    "readiness_voice",
                    "Character voice coverage is partial",
                    f"{len(unvoiced)} detected characters have no linked voice.",
                    chapter_id=chapter_id,
                    metadata={
                        "charactersDetected": len(characters),
                        "charactersVoiced": len(characters) - len(unvoiced),
                        "unvoicedCharacterIds": unvoiced[:20],
                    },
                )
            )
        elif characters:
            checks.append(
                self._passed(
                    "voice_character_coverage",
                    "voice",
                    f"{len(characters)} detected characters have linked voices.",
                )
            )
        else:
            checks.append(
                self._issue(
                    "voice_no_characters_detected",
                    "voice",
                    "warning",
                    "readiness_voice",
                    "No cast has been detected",
                    "Run Structure & Cast Draft before chapter production review.",
                    chapter_id=chapter_id,
                    metadata={"charactersDetected": 0, "charactersVoiced": 0},
                )
            )

        if segment_ids:
            speaker_rows = list(
                session.scalars(
                    select(SpeakerAttributionRecord).where(
                        SpeakerAttributionRecord.project_id == project_id,
                        SpeakerAttributionRecord.segment_id.in_(segment_ids),
                        SpeakerAttributionRecord.status == "approved",
                    )
                )
            )
            narrator_fallback = len(
                [
                    row
                    for row in speaker_rows
                    if row.character_id is None or row.character_id not in voiced_character_ids
                ]
            )
            if narrator_fallback:
                checks.append(
                    self._issue(
                        "voice_narrator_fallback_rows",
                        "voice",
                        "warning",
                        "readiness_voice",
                        "Narrator fallback will be used",
                        f"{narrator_fallback} approved rows will use the narrator voice.",
                        chapter_id=chapter_id,
                        metadata={"narratorFallbackRows": narrator_fallback},
                    )
                )
            else:
                checks.append(
                    self._passed(
                        "voice_narrator_fallback_rows",
                        "voice",
                        "No approved cast rows need narrator fallback.",
                    )
                )
        return checks

    def _direction_checks(
        self, session: Session, project_id: str, segment_ids: list[str], chapter_id: str | None
    ) -> list[CheckDraft]:
        if not segment_ids:
            return []
        count = self._count(
            session,
            select(func.count()).select_from(SegmentDirectionRecord).where(
                SegmentDirectionRecord.project_id == project_id,
                SegmentDirectionRecord.segment_id.in_(segment_ids),
            ),
        )
        missing = len(segment_ids) - count
        if missing:
            return [
                self._issue(
                    "direction_missing",
                    "direction",
                    "warning",
                    "readiness_direction",
                    "Direction coverage is partial",
                    f"{missing} segments will use default narration direction.",
                    chapter_id=chapter_id,
                    metadata={"missingDirections": missing},
                )
            ]
        return [self._passed("direction_coverage", "direction", "All segments have direction rows.")]

    def _audio_checks(
        self,
        session: Session,
        project_id: str,
        chapters: list[ChapterRecord],
        segments: list[SegmentRecord],
    ) -> list[CheckDraft]:
        checks: list[CheckDraft] = []
        for chapter in chapters:
            try:
                status = ProductionService(self.container).status(project_id, chapter.id)
            except ValueError:
                continue
            if status.total_segments and status.current_segments < status.total_segments:
                checks.append(
                    self._issue(
                        f"stale_render_{chapter.id}",
                        "stale-render",
                        "warning",
                        "readiness_stale_render",
                        "Segment renders are stale",
                        f"{status.total_segments - status.current_segments} segments need rendering.",
                        chapter_id=chapter.id,
                        metadata={
                            "currentSegments": status.current_segments,
                            "totalSegments": status.total_segments,
                        },
                    )
                )
            render = session.scalar(
                select(ChapterRenderRecord)
                .where(
                    ChapterRenderRecord.chapter_id == chapter.id,
                    ChapterRenderRecord.status == "succeeded",
                )
                .order_by(ChapterRenderRecord.created_at.desc(), ChapterRenderRecord.id.desc())
            )
            if not render:
                checks.append(
                    self._issue(
                        f"chapter_audio_missing_{chapter.id}",
                        "audio",
                        "blocking",
                        "readiness_audio",
                        "Chapter audio is missing",
                        "Produce or assemble this chapter before export.",
                        chapter_id=chapter.id,
                    )
                )
                continue
            audio_path = render.mixed_audio_path or render.speech_path
            audio_error = self._audio_error(audio_path, render.duration_ms)
            if audio_error:
                checks.append(
                    self._issue(
                        f"chapter_audio_invalid_{chapter.id}",
                        "audio",
                        "blocking",
                        "readiness_audio",
                        "Chapter audio artifact is invalid",
                        audio_error,
                        chapter_id=chapter.id,
                        metadata={"chapterRenderId": render.id},
                    )
                )
            else:
                checks.append(
                    self._passed(f"chapter_audio_{chapter.id}", "audio", "Chapter audio is readable.")
                )
        missing_segment_renders = self._missing_segment_renders(session, segments)
        if missing_segment_renders:
            checks.append(
                self._issue(
                    "segment_audio_missing",
                    "audio",
                    "warning",
                    "readiness_audio",
                    "Segment render history is incomplete",
                    f"{missing_segment_renders} segments have no successful segment render.",
                    metadata={"missingSegmentRenders": missing_segment_renders},
                )
            )
        return checks

    def _export_checks(
        self, session: Session, project_id: str, has_chapters: bool
    ) -> list[CheckDraft]:
        checks: list[CheckDraft] = []
        project = self.container.projects.get(project_id)
        if not project or project.rights_status.value != "declared":
            checks.append(
                self._issue(
                    "export_rights_missing",
                    "export-blocker",
                    "blocking",
                    "readiness_export",
                    "Rights declaration missing",
                    "Declared rights are required before export.",
                )
            )
        elif has_chapters:
            checks.append(self._passed("export_rights", "export-blocker", "Rights declaration is present."))
        open_blockers = self._count(
            session,
            select(func.count()).select_from(IssueRecord).where(
                IssueRecord.project_id == project_id,
                IssueRecord.severity == "blocking",
                IssueRecord.status == "open",
            ),
        )
        if open_blockers:
            checks.append(
                self._issue(
                    "export_open_blockers",
                    "export-blocker",
                    "blocking",
                    "readiness_export",
                    "Open blocking issues",
                    f"{open_blockers} blocking issues must be resolved or explicitly ignored.",
                    metadata={"openBlockingIssues": open_blockers},
                )
            )
        else:
            checks.append(self._passed("export_blockers", "export-blocker", "No open blocking issues."))
        return checks

    def _store_report(
        self, project_id: str, chapter_id: str | None, checks: list[ReadinessCheck]
    ) -> ReadinessReport:
        active = [
            check
            for check in checks
            if check.status != "passed" and (check.resolution_status in {None, "open"})
        ]
        blocking = len([check for check in active if check.severity == "blocking"])
        warnings = len([check for check in active if check.severity == "warning"])
        passed = len(checks) - len(active)
        status = "blocked" if blocking else "needs_review" if warnings else "ready"
        score = round((passed / len(checks)) * 100) if checks else 0
        summary = {
            "passed": passed,
            "warnings": warnings,
            "blocking": blocking,
            "total": len(checks),
        }
        record = ReadinessReportRecord(
            id=f"ready_{uuid4().hex[:16]}",
            project_id=project_id,
            chapter_id=chapter_id,
            status=status,
            score=score,
            summary_json=json.dumps(summary, sort_keys=True),
            checks_json=json.dumps(
                [check.model_dump(by_alias=True, mode="json") for check in checks],
                sort_keys=True,
            ),
            created_at=datetime.now(UTC),
        )
        with self.container.structure.database.session() as session:
            session.add(record)
            session.commit()
            return self._model(record)

    @staticmethod
    def _chapters(
        session: Session, project_id: str, chapter_id: str | None
    ) -> list[ChapterRecord]:
        query = select(ChapterRecord).where(ChapterRecord.project_id == project_id)
        if chapter_id:
            query = query.where(ChapterRecord.id == chapter_id)
        return list(session.scalars(query.order_by(ChapterRecord.order_index)))

    @staticmethod
    def _segments(session: Session, chapter_ids: list[str]) -> list[SegmentRecord]:
        if not chapter_ids:
            return []
        scene_ids = select(SceneRecord.id).where(SceneRecord.chapter_id.in_(chapter_ids))
        return list(
            session.scalars(
                select(SegmentRecord)
                .where(SegmentRecord.scene_id.in_(scene_ids))
                .order_by(SegmentRecord.scene_id, SegmentRecord.order_index)
            )
        )

    @staticmethod
    def _missing_segment_renders(session: Session, segments: list[SegmentRecord]) -> int:
        missing = 0
        for segment in segments:
            latest = session.scalar(
                select(SegmentRenderRecord.id).where(
                    SegmentRenderRecord.segment_id == segment.id,
                    SegmentRenderRecord.status == "succeeded",
                )
            )
            if not latest:
                missing += 1
        return missing

    @staticmethod
    def _audio_error(path: str, declared_duration_ms: int) -> str | None:
        audio_path = Path(path)
        if not audio_path.is_file():
            return "Expected chapter audio artifact is missing."
        try:
            with wave.open(str(audio_path), "rb") as audio:
                duration = int(audio.getnframes() / audio.getframerate() * 1000)
        except (EOFError, wave.Error):
            return "Chapter audio artifact cannot be decoded as WAV."
        if abs(duration - declared_duration_ms) > 100:
            return "Stored chapter duration differs from the WAV duration."
        return None

    @staticmethod
    def _passed(check_id: str, scope: str, description: str) -> CheckDraft:
        return CheckDraft(
            id=check_id,
            scope=scope,
            status="passed",
            severity="info",
            category=f"readiness_{scope.replace('-', '_')}",
            title="Passed",
            description=description,
        )

    @staticmethod
    def _issue(
        check_id: str,
        scope: str,
        severity: str,
        category: str,
        title: str,
        description: str,
        metadata: dict[str, object] | None = None,
        chapter_id: str | None = None,
        segment_id: str | None = None,
    ) -> CheckDraft:
        return CheckDraft(
            id=check_id,
            scope=scope,
            status="failed",
            severity=severity,
            category=category,
            title=title,
            description=description,
            chapter_id=chapter_id,
            segment_id=segment_id,
            metadata=metadata or {},
        )

    @staticmethod
    def _count(session: Session, statement: Any) -> int:
        value = session.scalar(statement)
        return int(value or 0)

    @staticmethod
    def _model(record: ReadinessReportRecord) -> ReadinessReport:
        return ReadinessReport(
            id=record.id,
            projectId=record.project_id,
            chapterId=record.chapter_id,
            status=record.status,
            score=record.score,
            summary=json.loads(record.summary_json),
            checks=[
                ReadinessCheck.model_validate(item)
                for item in json.loads(record.checks_json)
            ],
            createdAt=record.created_at,
        )
