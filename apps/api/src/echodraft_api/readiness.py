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

from .audio_analysis import AudioAnalysis, analyze_wav
from .container import AppContainer
from .production import ProductionService

# Mastering headroom target: -3 dBTP ceiling (see docs/plans/2026-07-04-phase-2-publishable-
# audio.md). Peaks hotter than this leave no room for the loudness-normalization/limiting
# pass that Phase 2 task B1 adds.
CHAPTER_PEAK_CEILING_DBFS = -3.0


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
            metadata = dict(draft.metadata)
            dedupe_key = f"readiness:{project_id}:{chapter_id or 'project'}:{draft.id}"
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
                    dedupe_key=dedupe_key,
                )
                issue_id = issue.id
                resolution_status = issue.status
                # A "resolved" mark is a claim, re-verified every run: a check that still
                # fails can never hide behind a stale resolution, so reopen it.
                if resolution_status == "resolved":
                    self.container.review.update_issue(issue.id, status="open", severity=None)
                    resolution_status = "open"
                    metadata["reopened"] = True
            else:
                # The condition now passes: auto-resolve any lingering issue for this check so
                # genuinely fixed findings (including previously accepted risks) clear themselves.
                existing = self.container.review.issue_by_dedupe_key(dedupe_key)
                if existing and existing.status != "resolved":
                    self.container.review.update_issue(
                        existing.id, status="resolved", severity=None
                    )
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
                    metadata=metadata,
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
                        "text_cleaning",
                        "text",
                        "warning",
                        "readiness_text",
                        "Open Clean Text Review issues",
                        f"{open_cleaning} clean-text issues are still open.",
                        {"openCleaningIssues": open_cleaning, "reason": "open_issues"},
                    )
                )
            else:
                checks.append(self._passed("text_cleaning", "text", "Clean text review has no open issues."))
        else:
            checks.append(
                self._issue(
                    "text_source",
                    "text",
                    "blocking",
                    "readiness_text",
                    "No imported source",
                    "Import a rights-cleared manuscript before readiness review.",
                    {"reason": "missing"},
                )
            )

        if not chapters:
            checks.append(
                self._issue(
                    "structure_chapters",
                    "structure",
                    "blocking",
                    "readiness_structure",
                    "No chapter structure",
                    "Extract structure before production readiness can pass.",
                    metadata={"reason": "missing"},
                )
            )
            return checks
        checks.append(self._passed("structure_chapters", "structure", f"{len(chapters)} chapters found."))
        if not segments:
            checks.append(
                self._issue(
                    "structure_segments",
                    "structure",
                    "blocking",
                    "readiness_structure",
                    "No renderable segments",
                    "Chapters need scenes and segments before production.",
                    chapter_id=chapter_id,
                    metadata={"reason": "missing"},
                )
            )
        else:
            empty_segments = [segment.id for segment in segments if not segment.normalized_text.strip()]
            if empty_segments:
                checks.append(
                    self._issue(
                        "structure_segments",
                        "structure",
                        "warning",
                        "readiness_structure",
                        "Empty segments",
                        f"{len(empty_segments)} segments have no renderable text.",
                        chapter_id=chapter_id,
                        metadata={"segmentIds": empty_segments[:20], "reason": "empty"},
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
                    "structure_warnings",
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
                    "speaker_attribution",
                    "speaker",
                    "warning",
                    "readiness_speaker",
                    "Speaker review queue is open",
                    f"{review_count} speaker attribution rows still need review.",
                    chapter_id=chapter_id,
                    metadata={
                        "openSpeakerAttributions": review_count,
                        "unresolvedSpeakerRows": review_count,
                        "reason": "review_open",
                    },
                )
            ]
        if rows:
            return [self._passed("speaker_attribution", "speaker", "Speaker attributions are approved.")]
        return [
            self._issue(
                "speaker_attribution",
                "speaker",
                "warning",
                "readiness_speaker",
                "Speaker attribution has not run",
                "Run Cast Review before final export readiness.",
                chapter_id=chapter_id,
                metadata={"reason": "missing"},
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
                    "voice_narrator",
                    "voice",
                    "blocking",
                    "readiness_voice",
                    "Narrator voice missing",
                    "Choose a narrator voice before readiness can pass.",
                    metadata={"reason": "missing"},
                )
            )
        else:
            voice = session.get(VoiceProfileRecord, settings.narrator_voice_profile_id)
            if not voice or voice.project_id != project_id:
                checks.append(
                    self._issue(
                        "voice_narrator",
                        "voice",
                        "blocking",
                        "readiness_voice",
                        "Narrator voice is invalid",
                        "The selected narrator voice no longer exists in this project.",
                        metadata={"reason": "invalid"},
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
                        "reason": "partial",
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
                    "voice_character_coverage",
                    "voice",
                    "warning",
                    "readiness_voice",
                    "No cast has been detected",
                    "Run Structure & Cast Draft before chapter production review.",
                    chapter_id=chapter_id,
                    metadata={"charactersDetected": 0, "charactersVoiced": 0, "reason": "no_characters_detected"},
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
                    "direction_coverage",
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
                        f"chapter_audio_{chapter.id}",
                        "audio",
                        "blocking",
                        "readiness_audio",
                        "Chapter audio is missing",
                        "Produce or assemble this chapter before export.",
                        chapter_id=chapter.id,
                        metadata={"reason": "missing"},
                    )
                )
                continue
            audio_path = render.mixed_audio_path or render.speech_path
            analysis, audio_error = self._analyze_chapter_audio(audio_path, render.duration_ms)
            if audio_error:
                checks.append(
                    self._issue(
                        f"chapter_audio_{chapter.id}",
                        "audio",
                        "blocking",
                        "readiness_audio",
                        "Chapter audio artifact is invalid",
                        audio_error,
                        chapter_id=chapter.id,
                        metadata={"chapterRenderId": render.id, "reason": "invalid"},
                    )
                )
            else:
                checks.append(
                    self._passed(f"chapter_audio_{chapter.id}", "audio", "Chapter audio is readable.")
                )
            if analysis is not None:
                checks.append(self._chapter_audio_hot_check(chapter.id, analysis))
                checks.append(self._chapter_audio_dead_air_check(chapter.id, analysis))
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
                    "export_rights",
                    "export-blocker",
                    "blocking",
                    "readiness_export",
                    "Rights declaration missing",
                    "Declared rights are required before export.",
                    metadata={"reason": "missing"},
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
                    "export_blockers",
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
        accepted = [
            check
            for check in checks
            if check.status != "passed" and check.resolution_status in {"ignored", "locked"}
        ]
        blocking = len([check for check in active if check.severity == "blocking"])
        warnings = len([check for check in active if check.severity == "warning"])
        passed = len(checks) - len(active) - len(accepted)
        status = "blocked" if blocking else "needs_review" if warnings else "ready"
        score = round((passed / len(checks)) * 100) if checks else 0
        summary = {
            "passed": passed,
            "warnings": warnings,
            "blocking": blocking,
            "accepted": len(accepted),
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
    def _analyze_chapter_audio(
        path: str, declared_duration_ms: int
    ) -> tuple[AudioAnalysis | None, str | None]:
        """Decode+analyze once; the blocking readability check and the hot/dead-air warning
        checks all read from the same result instead of re-decoding the WAV three times.
        """
        audio_path = Path(path)
        if not audio_path.is_file():
            return None, "Expected chapter audio artifact is missing."
        try:
            analysis = analyze_wav(audio_path)
        except (EOFError, wave.Error, ValueError):
            return None, "Chapter audio artifact cannot be decoded as WAV."
        if abs(analysis.duration_ms - declared_duration_ms) > 100:
            return analysis, "Stored chapter duration differs from the WAV duration."
        return analysis, None

    @staticmethod
    def _chapter_audio_hot_check(chapter_id: str, analysis: AudioAnalysis) -> CheckDraft:
        check_id = f"chapter_audio_hot_{chapter_id}"
        if analysis.peak_dbfs > CHAPTER_PEAK_CEILING_DBFS:
            return ReadinessService._issue(
                check_id,
                "audio",
                "warning",
                "readiness_audio",
                "Chapter audio peak is too hot",
                f"Peak level is {analysis.peak_dbfs:.1f} dBFS, above the "
                f"{CHAPTER_PEAK_CEILING_DBFS:.0f} dBFS mastering ceiling.",
                chapter_id=chapter_id,
                metadata={"peakDbfs": analysis.peak_dbfs, "reason": "hot"},
            )
        return ReadinessService._passed(
            check_id,
            "audio",
            f"Chapter audio peak is within headroom ({analysis.peak_dbfs:.1f} dBFS).",
        )

    @staticmethod
    def _chapter_audio_dead_air_check(chapter_id: str, analysis: AudioAnalysis) -> CheckDraft:
        check_id = f"chapter_audio_dead_air_{chapter_id}"
        if analysis.dead_air_ranges:
            total_ms = sum(end - start for start, end in analysis.dead_air_ranges)
            longest_ms = max(end - start for start, end in analysis.dead_air_ranges)
            return ReadinessService._issue(
                check_id,
                "audio",
                "warning",
                "readiness_audio",
                "Chapter audio contains dead air",
                f"{len(analysis.dead_air_ranges)} dead-air stretch(es) totalling {total_ms} ms "
                f"(longest {longest_ms} ms).",
                chapter_id=chapter_id,
                metadata={
                    "deadAirRangeCount": len(analysis.dead_air_ranges),
                    "totalDeadAirMs": total_ms,
                    "longestDeadAirMs": longest_ms,
                    "reason": "dead_air_detected",
                },
            )
        return ReadinessService._passed(
            check_id, "audio", "No dead air detected in chapter audio."
        )

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
