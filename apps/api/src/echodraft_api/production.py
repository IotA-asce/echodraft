"""Chapter-at-a-time orchestration over immutable segment renders."""

import json

from echodraft_domain import (
    ChapterProductionStatus,
    ChapterRender,
    DirectionProfile,
    ProjectProductionSettings,
    SegmentProductionOverride,
    SegmentRenderRequest,
)
from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord, SegmentRenderRecord
from sqlalchemy import select

from .assembly import ChapterAssembler
from .container import AppContainer
from .rendering import SegmentRenderer


class ProductionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def settings(self, project_id: str) -> ProjectProductionSettings:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        record = self.container.production.get(project_id)
        return ProjectProductionSettings(
            projectId=project_id,
            narratorVoiceProfileId=record.narrator_voice_profile_id,
            defaultDirection=json.loads(record.default_direction_json)
            if record.default_direction_json
            else None,
        )

    def update_settings(
        self, project_id: str, narrator_voice_profile_id: str | None, direction: DirectionProfile | None
    ) -> ProjectProductionSettings:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        if narrator_voice_profile_id:
            profile = self.container.casting.voice(narrator_voice_profile_id)
            if not profile or profile.project_id != project_id:
                raise ValueError("Narrator voice profile does not belong to this project.")
        record = self.container.production.update(
            project_id,
            narrator_voice_profile_id,
            json.dumps(direction.model_dump(by_alias=True)) if direction else None,
        )
        return ProjectProductionSettings(
            projectId=project_id,
            narratorVoiceProfileId=record.narrator_voice_profile_id,
            defaultDirection=json.loads(record.default_direction_json)
            if record.default_direction_json
            else None,
        )

    def override(self, project_id: str, segment_id: str) -> SegmentProductionOverride:
        self._validate_segment_project(project_id, segment_id)
        record = self.container.production.override(segment_id)
        return SegmentProductionOverride(
            segmentId=segment_id,
            voiceProfileId=record.voice_profile_id if record else None,
            direction=json.loads(record.direction_json) if record and record.direction_json else None,
        )

    def update_override(
        self,
        project_id: str,
        segment_id: str,
        voice_profile_id: str | None,
        direction: DirectionProfile | None,
    ) -> SegmentProductionOverride:
        self._validate_segment_project(project_id, segment_id)
        if voice_profile_id:
            profile = self.container.casting.voice(voice_profile_id)
            if not profile or profile.project_id != project_id:
                raise ValueError("Segment voice profile does not belong to this project.")
        record = self.container.production.update_override(
            segment_id,
            voice_profile_id,
            json.dumps(direction.model_dump(by_alias=True)) if direction else None,
        )
        return SegmentProductionOverride(
            segmentId=record.segment_id,
            voiceProfileId=record.voice_profile_id,
            direction=json.loads(record.direction_json) if record.direction_json else None,
        )

    def status(self, project_id: str, chapter_id: str) -> ChapterProductionStatus:
        chapter = self.container.structure.chapter(chapter_id)
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")
        settings = self.settings(project_id)
        segments = self._segments(chapter_id)
        if not settings.narrator_voice_profile_id:
            return ChapterProductionStatus(
                chapterId=chapter_id, ready=False, reason="Choose a narrator voice before producing.",
                totalSegments=len(segments), currentSegments=0, activeRender=self._active(project_id, chapter_id),
            )
        overrides = self.container.production.overrides([segment.id for segment in segments])
        current = 0
        with self.container.structure.database.session() as session:
            for segment in segments:
                requested_voice = (
                    overrides[segment.id].voice_profile_id
                    if segment.id in overrides and overrides[segment.id].voice_profile_id
                    else settings.narrator_voice_profile_id
                )
                latest = session.scalar(
                    select(SegmentRenderRecord)
                    .where(SegmentRenderRecord.segment_id == segment.id, SegmentRenderRecord.status == "succeeded")
                    .order_by(SegmentRenderRecord.id.desc())
                )
                if latest:
                    payload = json.loads(latest.request_json)
                    if payload.get("revision") == segment.revision and payload.get("voiceProfileId") == requested_voice:
                        current += 1
        readiness = self.container.tts_settings.status()
        return ChapterProductionStatus(
            chapterId=chapter_id,
            ready=readiness.ready,
            reason=readiness.message,
            totalSegments=len(segments),
            currentSegments=current,
            activeRender=self._active(project_id, chapter_id),
        )

    def produce(self, project_id: str, chapter_id: str, job_id: str, force: bool = False) -> None:
        status = self.status(project_id, chapter_id)
        if not status.ready:
            raise ValueError(status.reason or "Chapter is not ready for production.")
        settings = self.settings(project_id)
        assert settings.narrator_voice_profile_id
        segments = self._segments(chapter_id)
        overrides = self.container.production.overrides([segment.id for segment in segments])
        renderer = SegmentRenderer(self.container)
        for index, segment in enumerate(segments, 1):
            override = overrides.get(segment.id)
            voice = override.voice_profile_id if override and override.voice_profile_id else settings.narrator_voice_profile_id
            direction = (
                DirectionProfile.model_validate(json.loads(override.direction_json))
                if override and override.direction_json
                else settings.default_direction
            )
            if not direction:
                direction = DirectionProfile(scopeType="segment", scopeId=segment.id)
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "rendering", "current": index, "total": len(segments), "segmentId": segment.id},
            )
            renderer.render(
                project_id,
                segment.id,
                SegmentRenderRequest(voiceProfileId=voice, direction=direction, force=force),
            )
        self.container.jobs_repository.set_progress(job_id, {"phase": "assembling", "current": len(segments), "total": len(segments)})
        ChapterAssembler(self.container).assemble(project_id, chapter_id, "speech_only")
        self.container.jobs_repository.set_progress(job_id, {"phase": "completed", "current": len(segments), "total": len(segments)})

    def _segments(self, chapter_id: str) -> list[SegmentRecord]:
        with self.container.structure.database.session() as session:
            scenes = session.scalars(
                select(SceneRecord).where(SceneRecord.chapter_id == chapter_id).order_by(SceneRecord.order_index)
            )
            result: list[SegmentRecord] = []
            for scene in scenes:
                result.extend(
                    session.scalars(
                        select(SegmentRecord)
                        .where(SegmentRecord.scene_id == scene.id)
                        .order_by(SegmentRecord.order_index)
                    )
                )
            return result

    def _validate_segment_project(self, project_id: str, segment_id: str) -> None:
        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Segment or project not found.")

    def _active(self, project_id: str, chapter_id: str) -> ChapterRender | None:
        try:
            return ChapterAssembler(self.container).active(project_id, chapter_id)
        except ValueError:
            return None
