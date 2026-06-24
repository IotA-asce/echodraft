import json
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from echodraft_domain import ChapterRender
from echodraft_db.models import (
    ChapterRenderRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRenderRecord,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .container import AppContainer
from .review import ReviewService


@dataclass(frozen=True)
class AssemblyInput:
    scene_id: str
    segment: SegmentRecord
    render: SegmentRenderRecord


class ChapterAssembler:
    """Build immutable chapter stems from the current successful segment renders."""

    sample_rate = 16_000
    channels = 1
    sample_width = 2
    paragraph_pause_ms = 350
    scene_pause_ms = 800

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def assemble(self, project_id: str, chapter_id: str) -> ChapterRender:
        project = self.container.projects.get(project_id)
        chapter = self.container.structure.chapter(chapter_id)
        if not project or not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")

        with self.container.structure.database.session() as session:
            inputs = self._resolve_inputs(session, chapter_id)
            render_id = f"chaprend_{uuid4().hex[:16]}"
            root = Path(project.artifact_path) / "audio" / "chapters" / chapter_id / render_id
            root.mkdir(parents=True, exist_ok=True)
            speech_path = root / "speech.wav"
            duration_ms = self._write_speech_stem(speech_path, inputs)
            manifest_path = root / "chapter_render_manifest.json"
            waveform_path = root / "waveform.json"
            validation_path = root / "validation_report.json"

            manifest_path.write_text(
                json.dumps(
                    {
                        "chapterId": chapter_id,
                        "chapterRenderId": render_id,
                        "format": {
                            "sampleRate": self.sample_rate,
                            "channels": self.channels,
                            "sampleWidth": self.sample_width,
                        },
                        "pauses": {
                            "paragraphMs": self.paragraph_pause_ms,
                            "sceneMs": self.scene_pause_ms,
                        },
                        "inputs": [
                            {
                                "segmentId": item.segment.id,
                                "segmentRenderId": item.render.id,
                                "sceneId": item.scene_id,
                            }
                            for item in inputs
                        ],
                        "durationMs": duration_ms,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            waveform_path.write_text(json.dumps({"durationMs": duration_ms, "peaks": []}))
            validation_path.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "inputCount": len(inputs),
                        "warnings": [],
                        "output": str(speech_path),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            record = ChapterRenderRecord(
                id=render_id,
                chapter_id=chapter_id,
                status="succeeded",
                speech_path=str(speech_path),
                manifest_path=str(manifest_path),
                duration_ms=duration_ms,
            )
            session.add(record)
            session.commit()
        ReviewService(self.container).qa_chapter(
            project_id, chapter_id, record.id, record.speech_path, record.duration_ms
        )
        return self._model(record)

    def history(self, project_id: str, chapter_id: str) -> list[ChapterRender]:
        chapter = self.container.structure.chapter(chapter_id)
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")
        with self.container.structure.database.session() as session:
            records = list(
                session.scalars(
                    select(ChapterRenderRecord)
                    .where(ChapterRenderRecord.chapter_id == chapter_id)
                    .order_by(ChapterRenderRecord.id.desc())
                )
            )
        return [self._model(record) for record in records]

    def active(self, project_id: str, chapter_id: str) -> ChapterRender:
        history = self.history(project_id, chapter_id)
        if not history:
            raise ValueError("Chapter has no assembled render.")
        return history[0]

    def _resolve_inputs(self, session: Session, chapter_id: str) -> list[AssemblyInput]:
        # Ordering follows the authored scene and segment order, never filesystem order.
        scenes = list(
            session.scalars(
                select(SceneRecord)
                .where(SceneRecord.chapter_id == chapter_id)
                .order_by(SceneRecord.order_index)
            )
        )
        inputs: list[AssemblyInput] = []
        for scene in scenes:
            segments = session.scalars(
                select(SegmentRecord)
                .where(SegmentRecord.scene_id == scene.id)
                .order_by(SegmentRecord.order_index)
            )
            for segment in segments:
                if not segment.normalized_text.strip():
                    continue
                render = session.scalar(
                    select(SegmentRenderRecord)
                    .where(
                        SegmentRenderRecord.segment_id == segment.id,
                        SegmentRenderRecord.status == "succeeded",
                    )
                    .order_by(SegmentRenderRecord.id.desc())
                )
                if not render:
                    raise ValueError(f"Missing successful render for segment {segment.id}.")
                if not Path(render.audio_path).is_file():
                    raise ValueError(f"Audio artifact is missing for render {render.id}.")
                inputs.append(AssemblyInput(scene_id=scene.id, segment=segment, render=render))
        if not inputs:
            raise ValueError("Chapter has no renderable segments.")
        return inputs

    def _write_speech_stem(self, output_path: Path, inputs: list[AssemblyInput]) -> int:
        with wave.open(str(output_path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            for index, item in enumerate(inputs):
                target.writeframes(self._normalized_frames(Path(item.render.audio_path)))
                if index < len(inputs) - 1:
                    next_item = inputs[index + 1]
                    pause = (
                        self.scene_pause_ms
                        if item.scene_id != next_item.scene_id
                        else self.paragraph_pause_ms
                    )
                    target.writeframes(self._silence(pause))
        with wave.open(str(output_path)) as output:
            return int(output.getnframes() / output.getframerate() * 1000)

    def _normalized_frames(self, path: Path) -> bytes:
        with wave.open(str(path), "rb") as source:
            frames = source.readframes(source.getnframes())
            width = source.getsampwidth()
            channels = source.getnchannels()
            rate = source.getframerate()
        if channels < 1:
            raise ValueError(f"Unsupported channel count in {path}: {channels}.")
        if width not in {1, 2, 3, 4}:
            raise ValueError(f"Unsupported sample width in {path}: {width}.")
        samples = self._downmix_pcm(frames, width, channels)
        if rate != self.sample_rate:
            samples = self._resample(samples, rate)
        return struct.pack(f"<{len(samples)}h", *samples)

    def _downmix_pcm(self, frames: bytes, width: int, channels: int) -> list[int]:
        frame_size = width * channels
        samples: list[int] = []
        for offset in range(0, len(frames), frame_size):
            channel_values = [
                self._read_pcm_sample(
                    frames[offset + (channel * width) : offset + ((channel + 1) * width)], width
                )
                for channel in range(channels)
            ]
            samples.append(max(-32_768, min(32_767, round(sum(channel_values) / channels))))
        return samples

    @staticmethod
    def _read_pcm_sample(value: bytes, width: int) -> int:
        if width == 1:
            return (value[0] - 128) << 8
        raw = int.from_bytes(value, byteorder="little", signed=True)
        return raw >> (8 * (width - 2))

    def _resample(self, samples: list[int], source_rate: int) -> list[int]:
        if not samples:
            return []
        target_count = max(1, round(len(samples) * self.sample_rate / source_rate))
        converted: list[int] = []
        for index in range(target_count):
            position = index * source_rate / self.sample_rate
            lower = min(int(position), len(samples) - 1)
            upper = min(lower + 1, len(samples) - 1)
            fraction = position - lower
            converted.append(round(samples[lower] + ((samples[upper] - samples[lower]) * fraction)))
        return converted

    def _silence(self, duration_ms: int) -> bytes:
        frame_count = int(self.sample_rate * duration_ms / 1000)
        return b"\x00" * frame_count * self.channels * self.sample_width

    @staticmethod
    def _model(record: ChapterRenderRecord) -> ChapterRender:
        return ChapterRender(
            id=record.id,
            chapterId=record.chapter_id,
            status=record.status,
            speechPath=record.speech_path,
            manifestPath=record.manifest_path,
            durationMs=record.duration_ms,
        )
