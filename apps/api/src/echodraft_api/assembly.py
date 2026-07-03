import json
import struct
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from echodraft_domain import ChapterRender
from echodraft_db.models import (
    AmbienceAssetRecord,
    AmbienceCueRecord,
    ChapterRenderRecord,
    SceneRecord,
    SegmentRecord,
    SegmentRenderRecord,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from .container import AppContainer
from .review import ReviewService

# Serialize assembly per chapter so concurrent assemble() calls cannot interleave their
# input resolution and record insert, forking the append-only chapter render history.
# Keyed by chapter_id; _assemble_locks_guard protects the registry itself.
_assemble_locks: dict[str, threading.Lock] = {}
_assemble_locks_guard = threading.Lock()


def _chapter_assemble_lock(chapter_id: str) -> threading.Lock:
    with _assemble_locks_guard:
        lock = _assemble_locks.get(chapter_id)
        if lock is None:
            lock = threading.Lock()
            _assemble_locks[chapter_id] = lock
        return lock


@dataclass(frozen=True)
class AssemblyInput:
    scene_id: str
    segment: SegmentRecord
    render: SegmentRenderRecord
    # Pause spacing (ms) from the direction that actually rendered this segment.
    pause_before_ms: int = 0
    pause_after_ms: int = 0


@dataclass(frozen=True)
class SoundCueInput:
    id: str
    scene_id: str
    asset_id: str
    name: str
    asset_path: str
    asset_type: str
    cue_type: str
    start_ms: int
    gain_db: float
    fade_in_ms: int
    fade_out_ms: int
    ducking: bool
    render_mode: str
    no_sfx: bool


class ChapterAssembler:
    """Build immutable chapter stems from the current successful segment renders."""

    sample_rate = 16_000
    channels = 1
    sample_width = 2
    paragraph_pause_ms = 350
    scene_pause_ms = 800

    def __init__(self, container: AppContainer) -> None:
        self.container = container

    def assemble(
        self, project_id: str, chapter_id: str, render_mode: str = "speech_only"
    ) -> ChapterRender:
        render_mode = self._canonical_render_mode(render_mode)
        if render_mode not in {"speech_only", "multi_voice", "light_cinematic", "dramatized"}:
            raise ValueError("Unsupported render mode.")
        project = self.container.projects.get(project_id)
        chapter = self.container.structure.chapter(chapter_id)
        if not project or not chapter or chapter.project_id != project_id:
            raise ValueError("Chapter or project not found.")

        with (
            _chapter_assemble_lock(chapter_id),
            self.container.structure.database.session() as session,
        ):
            inputs = self._resolve_inputs(session, chapter_id)
            render_id = f"chaprend_{uuid4().hex[:16]}"
            root = Path(project.artifact_path) / "audio" / "chapters" / chapter_id / render_id
            root.mkdir(parents=True, exist_ok=True)
            speech_path = root / "speech.wav"
            duration_ms, scene_offsets, applied_pauses = self._write_speech_stem(
                speech_path, inputs
            )
            ambience_path = None
            mixed_path = None
            sound_cues: list[SoundCueInput] = []
            mix_warnings: list[str] = []
            if render_mode in {"light_cinematic", "dramatized"}:
                sound_cues = self._resolve_sound_cues(session, chapter_id, render_mode)
                ambience_path = root / "sound-design.wav"
                mixed_path = root / "mix.wav"
                mix_warnings = self._write_sound_mix(
                    speech_path,
                    ambience_path,
                    mixed_path,
                    duration_ms,
                    scene_offsets,
                    sound_cues,
                    render_mode,
                )
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
                            "applied": applied_pauses,
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
                        "renderMode": render_mode,
                        "ambienceInputs": [self._sound_cue_manifest(item) for item in sound_cues],
                        "soundDesign": {
                            "mode": self._public_render_mode(render_mode),
                            "cleanNarrationDefault": render_mode == "speech_only",
                            "cueCount": len(sound_cues),
                            "outputs": {
                                "speech": str(speech_path),
                                "soundStem": str(ambience_path) if ambience_path else None,
                                "mix": str(mixed_path) if mixed_path else None,
                            },
                            "warnings": mix_warnings,
                        },
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
                        "warnings": mix_warnings,
                        "output": str(mixed_path or speech_path),
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
                render_mode=render_mode,
                ambience_stem_path=str(ambience_path) if ambience_path else None,
                mixed_audio_path=str(mixed_path) if mixed_path else None,
            )
            session.add(record)
            session.commit()
        ReviewService(self.container).qa_chapter(
            project_id,
            chapter_id,
            record.id,
            record.mixed_audio_path or record.speech_path,
            record.duration_ms,
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
                    .order_by(
                        ChapterRenderRecord.created_at.desc(), ChapterRenderRecord.id.desc()
                    )
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
                    .order_by(
                        SegmentRenderRecord.created_at.desc(), SegmentRenderRecord.id.desc()
                    )
                )
                if not render:
                    raise ValueError(f"Missing successful render for segment {segment.id}.")
                try:
                    request_payload = json.loads(render.request_json)
                except json.JSONDecodeError:
                    request_payload = {}
                render_revision = request_payload.get("revision")
                if render_revision != segment.revision:
                    raise ValueError(
                        f"Stale render for segment {segment.id}: render revision "
                        f"{render_revision} does not match segment revision "
                        f"{segment.revision}. Re-render before assembling."
                    )
                if not Path(render.audio_path).is_file():
                    raise ValueError(f"Audio artifact is missing for render {render.id}.")
                # Pauses come from the direction that actually rendered (stored with
                # by-alias keys), never a re-derived direction, and are clamped to the
                # DirectionProfile bounds so a corrupt payload cannot inject silence.
                direction_payload = request_payload.get("direction") or {}
                pause_before_ms = self._clamp_pause(direction_payload.get("pauseBeforeMs"))
                pause_after_ms = self._clamp_pause(direction_payload.get("pauseAfterMs"))
                inputs.append(
                    AssemblyInput(
                        scene_id=scene.id,
                        segment=segment,
                        render=render,
                        pause_before_ms=pause_before_ms,
                        pause_after_ms=pause_after_ms,
                    )
                )
        if not inputs:
            raise ValueError("Chapter has no renderable segments.")
        return inputs

    def _clamp_pause(self, value: object) -> int:
        # Mirror DirectionProfile's 0–5000 ms bounds; ignore non-numeric payloads.
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return 0
        return max(0, min(5000, int(value)))

    def _write_speech_stem(
        self, output_path: Path, inputs: list[AssemblyInput]
    ) -> tuple[int, dict[str, int], list[dict[str, object]]]:
        frame_cursor = 0
        scene_offsets: dict[str, int] = {}
        applied_pauses: list[dict[str, object]] = []
        with wave.open(str(output_path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            for index, item in enumerate(inputs):
                scene_offsets.setdefault(item.scene_id, self._frames_to_ms(frame_cursor))
                frames = self._normalized_frames(Path(item.render.audio_path))
                target.writeframes(frames)
                frame_cursor += self._frame_count(frames)
                if index < len(inputs) - 1:
                    next_item = inputs[index + 1]
                    # A scene boundary keeps its 800 ms floor; within a scene the
                    # paragraph default applies. The larger of that default and either
                    # side's requested pause wins so deliberate silences are honored.
                    default_gap = (
                        self.scene_pause_ms
                        if item.scene_id != next_item.scene_id
                        else self.paragraph_pause_ms
                    )
                    pause = max(
                        item.pause_after_ms, next_item.pause_before_ms, default_gap
                    )
                    silence = self._silence(pause)
                    target.writeframes(silence)
                    frame_cursor += self._frame_count(silence)
                    applied_pauses.append({"afterSegmentId": item.segment.id, "ms": pause})
        return self._frames_to_ms(frame_cursor), scene_offsets, applied_pauses

    def _resolve_sound_cues(
        self, session: Session, chapter_id: str, render_mode: str
    ) -> list[SoundCueInput]:
        statement = (
            select(AmbienceCueRecord, AmbienceAssetRecord)
            .join(AmbienceAssetRecord, AmbienceAssetRecord.id == AmbienceCueRecord.asset_id)
            .join(SceneRecord, SceneRecord.id == AmbienceCueRecord.scene_id)
            .where(SceneRecord.chapter_id == chapter_id)
            .order_by(SceneRecord.order_index, AmbienceCueRecord.start_ms)
        )
        resolved: list[SoundCueInput] = []
        for cue, asset in session.execute(statement).all():
            cue_mode = cue.render_mode or "light"
            if render_mode == "light_cinematic" and cue_mode not in {"light", "all", "light_cinematic"}:
                continue
            if render_mode == "dramatized" and cue_mode not in {
                "light",
                "all",
                "light_cinematic",
                "dramatized",
            }:
                continue
            resolved.append(
                SoundCueInput(
                    id=cue.id,
                    scene_id=cue.scene_id,
                    asset_id=asset.id,
                    name=asset.name,
                    asset_path=asset.asset_path,
                    asset_type=asset.asset_type,
                    cue_type=cue.cue_type,
                    start_ms=cue.start_ms,
                    gain_db=cue.gain_db,
                    fade_in_ms=cue.fade_in_ms,
                    fade_out_ms=cue.fade_out_ms,
                    ducking=cue.ducking,
                    render_mode=cue_mode,
                    no_sfx=cue.no_sfx,
                )
            )
        return resolved

    def _write_sound_mix(
        self,
        speech_path: Path,
        stem_path: Path,
        mixed_path: Path,
        duration_ms: int,
        scene_offsets: dict[str, int],
        cues: list[SoundCueInput],
        render_mode: str,
    ) -> list[str]:
        speech_samples = self._samples_from_wav(speech_path)
        target_length = max(len(speech_samples), int(self.sample_rate * duration_ms / 1000))
        if len(speech_samples) < target_length:
            speech_samples.extend([0] * (target_length - len(speech_samples)))
        sound_stem = [0.0] * target_length
        warnings: list[str] = []
        for cue in cues:
            if cue.no_sfx and (cue.asset_type == "sfx" or cue.cue_type == "sfx"):
                warnings.append(f"Skipped SFX cue {cue.id} because noSfx is set.")
                continue
            asset_path = Path(cue.asset_path)
            if not asset_path.is_file():
                warnings.append(f"Skipped cue {cue.id}; asset file is missing.")
                continue
            try:
                asset_samples = self._samples_from_wav(asset_path)
            except (wave.Error, ValueError, OSError) as error:
                warnings.append(f"Skipped cue {cue.id}; asset is not a readable WAV: {error}.")
                continue
            if not asset_samples:
                warnings.append(f"Skipped cue {cue.id}; asset contains no audio frames.")
                continue
            start_frame = int(
                self.sample_rate * ((scene_offsets.get(cue.scene_id, 0) + cue.start_ms) / 1000)
            )
            if start_frame >= target_length:
                warnings.append(f"Skipped cue {cue.id}; start time is beyond the chapter length.")
                continue
            cue_samples = self._cue_samples(asset_samples, target_length - start_frame, cue)
            gain = self._cue_gain(cue, render_mode)
            fade_in_frames = int(self.sample_rate * max(0, cue.fade_in_ms) / 1000)
            fade_out_frames = int(self.sample_rate * max(0, cue.fade_out_ms) / 1000)
            for offset, sample in enumerate(cue_samples):
                position = start_frame + offset
                if position >= target_length:
                    break
                envelope = 1.0
                if fade_in_frames and offset < fade_in_frames:
                    envelope = min(envelope, offset / fade_in_frames)
                if fade_out_frames and offset >= len(cue_samples) - fade_out_frames:
                    remaining = max(0, len(cue_samples) - offset)
                    envelope = min(envelope, remaining / fade_out_frames)
                sound_stem[position] += sample * gain * envelope
        stem_samples = [self._clip_sample(round(value)) for value in sound_stem]
        mixed_samples = [
            self._clip_sample(speech + stem) for speech, stem in zip(speech_samples, stem_samples)
        ]
        self._write_samples(stem_path, stem_samples)
        self._write_samples(mixed_path, mixed_samples)
        return warnings

    def _cue_samples(
        self, asset_samples: list[int], max_frames: int, cue: SoundCueInput
    ) -> list[int]:
        if cue.asset_type in {"ambience", "music"} or cue.cue_type in {"ambience", "music"}:
            repeated: list[int] = []
            while len(repeated) < max_frames:
                repeated.extend(asset_samples[: max_frames - len(repeated)])
            return repeated[:max_frames]
        return asset_samples[:max_frames]

    @staticmethod
    def _cue_gain(cue: SoundCueInput, render_mode: str) -> float:
        if render_mode == "light_cinematic":
            maximum = -14.0 if cue.asset_type == "sfx" or cue.cue_type == "sfx" else -18.0
        else:
            maximum = -10.0 if cue.asset_type == "sfx" or cue.cue_type == "sfx" else -14.0
        gain_db = min(cue.gain_db, maximum)
        if cue.ducking:
            gain_db -= 6.0
        return 10 ** (gain_db / 20)

    def _samples_from_wav(self, path: Path) -> list[int]:
        frames = self._normalized_frames(path)
        if not frames:
            return []
        return list(struct.unpack(f"<{len(frames) // self.sample_width}h", frames))

    def _write_samples(self, path: Path, samples: list[int]) -> None:
        with wave.open(str(path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            target.writeframes(struct.pack(f"<{len(samples)}h", *samples))

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

    def _write_silence_stem(self, path: Path, duration_ms: int) -> None:
        with wave.open(str(path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            target.writeframes(self._silence(duration_ms))

    def _frame_count(self, frames: bytes) -> int:
        return len(frames) // (self.channels * self.sample_width)

    def _frames_to_ms(self, frame_count: int) -> int:
        return int(frame_count / self.sample_rate * 1000)

    @staticmethod
    def _clip_sample(value: float | int) -> int:
        return max(-32_768, min(32_767, round(value)))

    @staticmethod
    def _canonical_render_mode(render_mode: str) -> str:
        aliases = {
            "clean": "speech_only",
            "light": "light_cinematic",
            "light_cinematic": "light_cinematic",
            "speech_only": "speech_only",
            "multi_voice": "multi_voice",
            "dramatized": "dramatized",
        }
        return aliases.get(render_mode, render_mode)

    @staticmethod
    def _public_render_mode(render_mode: str) -> str:
        if render_mode == "speech_only":
            return "clean"
        if render_mode == "light_cinematic":
            return "light"
        return render_mode

    @staticmethod
    def _sound_cue_manifest(cue: SoundCueInput) -> dict[str, object]:
        return {
            "id": cue.id,
            "sceneId": cue.scene_id,
            "assetId": cue.asset_id,
            "assetName": cue.name,
            "assetType": cue.asset_type,
            "cueType": cue.cue_type,
            "startMs": cue.start_ms,
            "gainDb": cue.gain_db,
            "fadeInMs": cue.fade_in_ms,
            "fadeOutMs": cue.fade_out_ms,
            "ducking": cue.ducking,
            "renderMode": cue.render_mode,
            "noSfx": cue.no_sfx,
        }

    @staticmethod
    def _model(record: ChapterRenderRecord) -> ChapterRender:
        return ChapterRender(
            id=record.id,
            chapterId=record.chapter_id,
            status=record.status,
            speechPath=record.speech_path,
            manifestPath=record.manifest_path,
            durationMs=record.duration_ms,
            renderMode=record.render_mode,
            ambienceStemPath=record.ambience_stem_path,
            mixedAudioPath=record.mixed_audio_path,
            createdAt=record.created_at,
        )
