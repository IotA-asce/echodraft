import hashlib
import json
import wave
from pathlib import Path
from uuid import uuid4
from echodraft_domain import SegmentRender, SegmentRenderRequest
from echodraft_db.models import SegmentRenderRecord
from sqlalchemy import select
from .container import AppContainer
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
        payload = {
            "text": segment.normalized_text,
            "revision": segment.revision,
            "voice": request.voice_profile_id,
            "direction": request.direction.model_dump(by_alias=True),
            "format": request.output_format,
            "adapter": "mock-0.1",
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        root = Path(project.artifact_path) / "audio" / "segments" / segment_id / key
        root.mkdir(parents=True, exist_ok=True)
        audio = root / "speech.wav"
        metadata = root / "metadata.json"
        provenance = self.adapter.preview(
            segment.normalized_text, request.voice_profile_id, audio, request.direction
        )
        with wave.open(str(audio)) as wav:
            duration = int(wav.getnframes() / wav.getframerate() * 1000)
        metadata.write_text(
            json.dumps(
                {
                    **payload,
                    "tts": provenance,
                    "renderKey": key,
                    "durationMs": duration,
                    "sampleRate": 16000,
                    "peak": 0,
                    "silenceRanges": [[0, duration]],
                    "waveform": [],
                },
                indent=2,
            )
        )
        with self.container.structure.database.session() as session:
            previous = session.scalar(
                select(SegmentRenderRecord)
                .where(
                    SegmentRenderRecord.segment_id == segment_id,
                    SegmentRenderRecord.status == "succeeded",
                )
                .order_by(SegmentRenderRecord.id.desc())
            )
        record = SegmentRenderRecord(
            id=f"rend_{uuid4().hex[:16]}",
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
        )
