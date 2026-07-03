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
from echodraft_db.models import (
    ChapterRecord,
    SceneRecord,
    SegmentDirectionRecord,
    SegmentProductionOverrideRecord,
    SegmentRecord,
)
from sqlalchemy import select

from .assembly import ChapterAssembler
from .container import AppContainer
from .direction import apply_pronunciations
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

    def resolve_voice(self, project_id: str, segment_id: str) -> str:
        """Resolve the voice a fresh render should use for one segment.

        Layering mirrors `status`/`produce`: segment production override wins, then the
        cast-resolved voice for approved speaker attributions, then the project narrator
        voice.
        """
        self._validate_segment_project(project_id, segment_id)
        settings = self.settings(project_id)
        override = self.container.production.override(segment_id)
        speaker_voices = self.container.speaker_attributions.resolved_voice_profiles([segment_id])
        voice = self._voice_for(segment_id, override, speaker_voices, settings.narrator_voice_profile_id)
        if not voice:
            raise ValueError("Set a narrator voice before patching.")
        return voice

    def resolve_direction(self, project_id: str, segment_id: str) -> DirectionProfile:
        """Resolve the direction a fresh render should use for one segment.

        Falls back through override -> saved segment direction -> project default -> a
        blank profile. Reuses `_direction_for` rather than duplicating it.
        """
        self._validate_segment_project(project_id, segment_id)
        settings = self.settings(project_id)
        override = self.container.production.override(segment_id)
        segment_directions = self.container.segment_directions.records([segment_id])
        return self._direction_for(
            segment_id, override, segment_directions, settings.default_direction
        )

    def resolve_voice_and_direction(
        self, project_id: str, segment_id: str
    ) -> tuple[str, DirectionProfile]:
        """Resolve both the voice and direction a fresh render should use for one segment.

        Kept for callers that need both regardless of what was already supplied; callers
        that already have one half (e.g. a patch payload that only supplies a voice) should
        call `resolve_voice`/`resolve_direction` individually instead, since resolving the
        unneeded half can raise unnecessarily (e.g. no narrator voice configured yet).
        """
        return self.resolve_voice(project_id, segment_id), self.resolve_direction(
            project_id, segment_id
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
        speaker_voices = self.container.speaker_attributions.resolved_voice_profiles(
            [segment.id for segment in segments]
        )
        segment_directions = self.container.segment_directions.records([segment.id for segment in segments])
        pronunciation_entries = self.container.casting.pronunciations(project_id)
        provider_identity = self.container.tts_adapter.render_identity()
        current = 0
        with self.container.structure.database.session() as session:
            for segment in segments:
                override = overrides.get(segment.id)
                requested_voice = self._voice_for(
                    segment.id, override, speaker_voices, settings.narrator_voice_profile_id
                )
                requested_direction = self._direction_for(
                    segment.id, override, segment_directions, settings.default_direction
                )
                latest = SegmentRenderer._latest_successful(session, segment.id)
                if latest:
                    payload = json.loads(latest.request_json)
                    synthesis_text, applied_pronunciations = apply_pronunciations(
                        segment.normalized_text, pronunciation_entries
                    )
                    if (
                        payload.get("revision") == segment.revision
                        and payload.get("synthesisText") == synthesis_text
                        and payload.get("pronunciationsApplied") == applied_pronunciations
                        and payload.get("voiceProfileId") == requested_voice
                        and payload.get("direction")
                        == requested_direction.model_dump(by_alias=True)
                        and payload.get("ttsProvider") == provider_identity
                    ):
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
        speaker_voices = self.container.speaker_attributions.resolved_voice_profiles(
            [segment.id for segment in segments]
        )
        segment_directions = self.container.segment_directions.records([segment.id for segment in segments])
        renderer = SegmentRenderer(self.container)
        for index, segment in enumerate(segments, 1):
            override = overrides.get(segment.id)
            voice = self._voice_for(segment.id, override, speaker_voices, settings.narrator_voice_profile_id)
            assert voice
            direction = self._direction_for(
                segment.id, override, segment_directions, settings.default_direction
            )
            self.container.jobs_repository.set_progress(
                job_id,
                {"phase": "rendering", "current": index, "total": len(segments), "segmentId": segment.id},
            )
            queue_item = self.container.render_queue.enqueue(
                project_id,
                chapter_id,
                segment.id,
                job_id,
                voice,
                self.container.tts_adapter.provider_id,
            )
            self.container.render_queue.mark_running(queue_item.id)
            try:
                render = renderer.render(
                    project_id,
                    segment.id,
                    SegmentRenderRequest(voiceProfileId=voice, direction=direction, force=force),
                )
            except Exception as error:
                self.container.render_queue.mark_failed(queue_item.id, str(error))
                raise
            self.container.render_queue.mark_succeeded(queue_item.id, render.render_key)
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

    @staticmethod
    def _voice_for(
        segment_id: str,
        override: SegmentProductionOverrideRecord | None,
        speaker_voices: dict[str, str],
        narrator_voice_profile_id: str | None,
    ) -> str | None:
        """Resolve the voice a segment should render with.

        Layering: segment production override wins, then the cast-resolved voice for
        approved speaker attributions, then the project narrator voice.
        """
        if override and override.voice_profile_id:
            return override.voice_profile_id
        return speaker_voices.get(segment_id, narrator_voice_profile_id)

    @staticmethod
    def _direction_for(
        segment_id: str,
        override: SegmentProductionOverrideRecord | None,
        segment_directions: dict[str, SegmentDirectionRecord],
        default_direction: DirectionProfile | None,
    ) -> DirectionProfile:
        direction_json = getattr(override, "direction_json", None)
        if direction_json:
            return DirectionProfile.model_validate(json.loads(direction_json))
        segment_direction = segment_directions.get(segment_id)
        if segment_direction:
            return DirectionProfile.model_validate(json.loads(segment_direction.direction_json))
        return default_direction or DirectionProfile(scopeType="segment", scopeId=segment_id)

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
