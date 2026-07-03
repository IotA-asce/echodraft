import hashlib
import json
import wave
from pathlib import Path
from uuid import uuid4
from echodraft_domain import SegmentRender, SegmentRenderComparison, SegmentRenderRequest
from echodraft_db.models import SegmentRenderRecord
from sqlalchemy import select
from sqlalchemy.orm import Session
from .container import AppContainer
from .direction import apply_pronunciations
from .review import ReviewService


class SegmentRenderer:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.adapter = container.tts_adapter

    def render(
        self, project_id: str, segment_id: str, request: SegmentRenderRequest
    ) -> SegmentRender:
        segment = self.container.structure.segment(segment_id)
        project = self.container.projects.get(project_id)
        if not segment or not project:
            raise ValueError("Segment or project not found.")
        provider_voice_id = self._resolve_voice(request.voice_profile_id)
        synthesis_text, pronunciations = apply_pronunciations(
            segment.normalized_text, self.container.casting.pronunciations(project_id)
        )
        provider_identity = self.adapter.render_identity()
        payload = {
            "text": segment.normalized_text,
            "synthesisText": synthesis_text,
            "revision": segment.revision,
            "voice": provider_voice_id,
            "voiceProfileId": request.voice_profile_id,
            "direction": request.direction.model_dump(by_alias=True),
            "format": request.output_format,
            "ttsProvider": provider_identity,
            "pronunciationsApplied": pronunciations,
        }
        if request.force:
            # Guarantee a distinct render_key for every forced render, even when nothing
            # about the effective inputs changed, so the render cache never silently
            # returns stale audio and (later) a succeeded (segment_id, render_key)
            # uniqueness index stays safe.
            payload["forceNonce"] = uuid4().hex
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if not request.force:
            with self.container.structure.database.session() as session:
                cached = session.scalar(
                    select(SegmentRenderRecord)
                    .where(
                        SegmentRenderRecord.segment_id == segment_id,
                        SegmentRenderRecord.render_key == key,
                        SegmentRenderRecord.status == "succeeded",
                    )
                    .order_by(
                        SegmentRenderRecord.created_at.desc(), SegmentRenderRecord.id.desc()
                    )
                )
            if cached:
                return self._model(cached)
        render_id = f"rend_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "audio" / "segments" / segment_id / key / render_id
        root.mkdir(parents=True, exist_ok=True)
        audio = root / "speech.wav"
        metadata = root / "metadata.json"
        provenance = self.adapter.preview(
            synthesis_text, provider_voice_id, audio, request.direction
        )
        with wave.open(str(audio)) as wav:
            duration = int(wav.getnframes() / wav.getframerate() * 1000)
            sample_rate = wav.getframerate()
        metadata.write_text(
            json.dumps(
                {
                    **payload,
                    "tts": provenance,
                    "renderKey": key,
                    "durationMs": duration,
                    "sampleRate": sample_rate,
                    "peak": 0,
                    "silenceRanges": [[0, duration]],
                    "waveform": [],
                },
                indent=2,
            )
        )
        with self.container.structure.database.session() as session:
            previous = self._latest_successful(session, segment_id)
        record = SegmentRenderRecord(
            id=render_id,
            segment_id=segment_id,
            render_key=key,
            status="succeeded",
            audio_path=str(audio),
            metadata_path=str(metadata),
            duration_ms=duration,
            parent_render_id=previous.id if previous else None,
            request_json=json.dumps(payload),
        )
        with self.container.structure.database.session() as s:
            s.add(record)
            s.commit()
        ReviewService(self.container).qa_segment(project_id, record)
        return SegmentRender(
            id=record.id,
            segmentId=segment_id,
            renderKey=key,
            status=record.status,
            audioPath=record.audio_path,
            metadataPath=record.metadata_path,
            durationMs=duration,
            parentRenderId=record.parent_render_id,
            createdAt=record.created_at,
        )

    def compare(self, project_id: str, segment_id: str) -> SegmentRenderComparison:
        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            from echodraft_db.models import ChapterRecord, SceneRecord

            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
            if not chapter or chapter.project_id != project_id:
                raise ValueError("Segment or project not found.")
            records = list(
                session.scalars(
                    select(SegmentRenderRecord)
                    .where(SegmentRenderRecord.segment_id == segment_id)
                )
            )
        current = self._tip(records)
        previous = next(
            (record for record in records if current and record.id == current.parent_render_id), None
        )
        changed = self._changed_fields(previous, current) if previous and current else []
        return SegmentRenderComparison(
            segmentId=segment_id,
            currentRender=self._model(current) if current else None,
            previousRender=self._model(previous) if previous else None,
            changedFields=changed,
        )

    def history(self, project_id: str, segment_id: str) -> list[SegmentRender]:
        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            from echodraft_db.models import ChapterRecord, SceneRecord

            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
            if not chapter or chapter.project_id != project_id:
                raise ValueError("Segment or project not found.")
            records = list(
                session.scalars(
                    select(SegmentRenderRecord)
                    .where(SegmentRenderRecord.segment_id == segment_id)
                    .order_by(
                        SegmentRenderRecord.created_at.desc(), SegmentRenderRecord.id.desc()
                    )
                )
            )
        return [self._model(record) for record in records]

    def _resolve_voice(self, requested_voice: str) -> str:
        profile = self.container.casting.voice(requested_voice)
        return profile.provider_voice_id if profile and profile.provider_voice_id else requested_voice

    @staticmethod
    def _changed_fields(
        previous: SegmentRenderRecord | None, current: SegmentRenderRecord | None
    ) -> list[str]:
        if not previous or not current:
            return []
        try:
            before = json.loads(previous.request_json)
            after = json.loads(current.request_json)
        except json.JSONDecodeError:
            return ["request"]
        fields = [
            "text",
            "synthesisText",
            "revision",
            "voiceProfileId",
            "direction",
            "ttsProvider",
            "pronunciationsApplied",
        ]
        return [field for field in fields if before.get(field) != after.get(field)]

    @staticmethod
    def _latest_successful(session: Session, segment_id: str) -> SegmentRenderRecord | None:
        records = list(
            session.scalars(
                select(SegmentRenderRecord)
                .where(
                    SegmentRenderRecord.segment_id == segment_id,
                    SegmentRenderRecord.status == "succeeded",
                )
                .order_by(SegmentRenderRecord.created_at, SegmentRenderRecord.id)
            )
        )
        return SegmentRenderer._tip(records)

    @staticmethod
    def _tip(records: list[SegmentRenderRecord]) -> SegmentRenderRecord | None:
        if not records:
            return None
        parent_ids = {record.parent_render_id for record in records if record.parent_render_id}
        tips = [record for record in records if record.id not in parent_ids]
        return tips[-1] if tips else records[-1]

    @staticmethod
    def _model(record: SegmentRenderRecord) -> SegmentRender:
        return SegmentRender(
            id=record.id,
            segmentId=record.segment_id,
            renderKey=record.render_key,
            status=record.status,
            audioPath=record.audio_path,
            metadataPath=record.metadata_path,
            durationMs=record.duration_ms,
            parentRenderId=record.parent_render_id,
            createdAt=record.created_at,
        )
