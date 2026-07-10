import json
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
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

from . import mastering
from .audio_analysis import AudioAnalysis, _decode_pcm, analyze_wav
from .container import AppContainer
from .review import ReviewService

# Ambience loop seams get a 250 ms equal-power crossfade; cue ducking dips -6 dB but the
# transition is ramped over 50 ms so the gain change never "zips".
AMBIENCE_CROSSFADE_MS = 250
DUCK_RAMP_MS = 50
DUCK_ATTENUATION_DB = -6.0


def band_limited_resample(
    samples: np.ndarray, source_rate: int, target_rate: int
) -> np.ndarray:
    """Resample ``samples`` via the Fourier method (ideal band-limited interpolation).

    Zero-padding the spectrum when upsampling introduces no energy above the source
    Nyquist (so a 16 kHz render carries no alias images into the 44.1 kHz band);
    truncating it when downsampling acts as an ideal anti-alias low-pass. This is the
    numpy fallback used whenever ffmpeg's soxr resampler is unavailable at render time.
    Returns a float64 array; callers clip/round to PCM16.
    """
    samples = np.asarray(samples, dtype=np.float64)
    n_in = samples.size
    if n_in == 0 or source_rate == target_rate:
        return samples.copy()
    n_out = max(1, int(round(n_in * target_rate / source_rate)))
    spectrum = np.fft.rfft(samples)
    n_freq_out = n_out // 2 + 1
    resized = np.zeros(n_freq_out, dtype=complex)
    copy = min(spectrum.size, n_freq_out)
    resized[:copy] = spectrum[:copy]
    return np.fft.irfft(resized, n=n_out) * (n_out / n_in)

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

    sample_rate = 44_100
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
            duration_ms, scene_offsets, applied_pauses, timeline = self._write_speech_stem(
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
            output_path = mixed_path or speech_path
            # Master the deliverable in place: lay ~-70 dBFS room tone at the head/tail
            # (ACX rejects pure digital silence) and, when ffmpeg is present, loudness-
            # normalise to -19 LUFS and true-peak-limit to -3 dBTP. Without ffmpeg the room-
            # toned 44.1 kHz bed is written un-mastered and the manifest records
            # "mastered": false so export readiness can raise the honest ffmpeg blocker
            # instead of shipping a falsely-labelled master.
            mastered, measured = self._apply_mastering(output_path)
            timeline = [
                {
                    **entry,
                    "startMs": self._int_manifest_value(entry.get("startMs")) + mastering.ROOM_TONE_HEAD_MS,
                    "endMs": self._int_manifest_value(entry.get("endMs")) + mastering.ROOM_TONE_HEAD_MS,
                }
                for entry in timeline
            ]

            manifest_path = root / "chapter_render_manifest.json"
            waveform_path = root / "waveform.json"
            validation_path = root / "validation_report.json"

            # Decode the mastered output exactly once; the duration, the waveform, the
            # validation report, and chapter QA (below) all consume this same analysis. A
            # WAV we just wrote but cannot re-read is reported honestly as a failed
            # validation, never an unhandled crash after the audio work already succeeded.
            analysis: AudioAnalysis | None
            try:
                analysis = analyze_wav(output_path)
            except (EOFError, wave.Error, ValueError):
                analysis = None
            # Room tone + mastering change the sample count, so the stored duration is the
            # final decoded duration; the pre-master stem duration only drove the mixing.
            if analysis is not None:
                duration_ms = analysis.duration_ms
            if analysis is None:
                findings = [
                    ("corrupt_audio", "blocking", "Audio artifact cannot be decoded as WAV.")
                ]
            else:
                findings = ReviewService._audio_rules(output_path, duration_ms, analysis=analysis)

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
                        "timeline": timeline,
                        "durationMs": duration_ms,
                        "renderMode": render_mode,
                        "ambienceInputs": [self._sound_cue_manifest(item) for item in sound_cues],
                        "mastering": {
                            "targetLufs": mastering.TARGET_LUFS,
                            "truePeakDb": mastering.TRUE_PEAK_DB,
                            "lra": mastering.TARGET_LRA,
                            "mastered": mastered,
                            "roomToneMs": {
                                "head": mastering.ROOM_TONE_HEAD_MS,
                                "tail": mastering.ROOM_TONE_TAIL_MS,
                            },
                            "measured": self._mastering_measurement(measured),
                        },
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
            waveform_path.write_text(
                json.dumps(
                    {
                        "durationMs": duration_ms,
                        "peaks": analysis.waveform_peaks if analysis else [],
                    }
                )
            )
            validation_path.write_text(
                json.dumps(
                    {
                        "status": (
                            "failed"
                            if any(severity == "blocking" for _, severity, _ in findings)
                            else "passed"
                        ),
                        "inputCount": len(inputs),
                        "warnings": mix_warnings,
                        "findings": [
                            {"category": category, "severity": severity, "description": description}
                            for category, severity, description in findings
                        ],
                        "output": str(output_path),
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
        mastered_lufs: float | None = None
        if mastered and measured:
            try:
                mastered_lufs = float(measured["input_i"])
            except (KeyError, ValueError):
                mastered_lufs = None
        ReviewService(self.container).qa_chapter(
            project_id,
            chapter_id,
            record.id,
            record.mixed_audio_path or record.speech_path,
            record.duration_ms,
            analysis=analysis,
            mastered_lufs=mastered_lufs,
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
    ) -> tuple[int, dict[str, int], list[dict[str, object]], list[dict[str, object]]]:
        frame_cursor = 0
        scene_offsets: dict[str, int] = {}
        applied_pauses: list[dict[str, object]] = []
        timeline: list[dict[str, object]] = []
        with wave.open(str(output_path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            for index, item in enumerate(inputs):
                scene_offsets.setdefault(item.scene_id, self._frames_to_ms(frame_cursor))
                frames = self._normalized_frames(Path(item.render.audio_path))
                start_ms = self._frames_to_ms(frame_cursor)
                target.writeframes(frames)
                frame_cursor += self._frame_count(frames)
                timeline.append(
                    {
                        "segmentId": item.segment.id,
                        "segmentRenderId": item.render.id,
                        "sceneId": item.scene_id,
                        "startMs": start_ms,
                        "endMs": self._frames_to_ms(frame_cursor),
                    }
                )
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
        return self._frames_to_ms(frame_cursor), scene_offsets, applied_pauses, timeline

    def _resolve_sound_cues(
        self, session: Session, chapter_id: str, render_mode: str
    ) -> list[SoundCueInput]:
        statement = (
            select(AmbienceCueRecord, AmbienceAssetRecord)
            .join(AmbienceAssetRecord, AmbienceAssetRecord.id == AmbienceCueRecord.asset_id)
            .join(SceneRecord, SceneRecord.id == AmbienceCueRecord.scene_id)
            .where(SceneRecord.chapter_id == chapter_id)
            .where(AmbienceCueRecord.muted.is_(False))
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
        speech = self._read_samples_array(speech_path).astype(np.float64)
        target_length = max(speech.size, int(self.sample_rate * duration_ms / 1000))
        if speech.size < target_length:
            speech = np.pad(speech, (0, target_length - speech.size))
        stem = np.zeros(target_length, dtype=np.float64)
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
                asset = self._read_samples_array(asset_path).astype(np.float64)
            except (wave.Error, ValueError, OSError) as error:
                warnings.append(f"Skipped cue {cue.id}; asset is not a readable WAV: {error}.")
                continue
            if asset.size == 0:
                warnings.append(f"Skipped cue {cue.id}; asset contains no audio frames.")
                continue
            start_frame = int(
                self.sample_rate * ((scene_offsets.get(cue.scene_id, 0) + cue.start_ms) / 1000)
            )
            if start_frame >= target_length:
                warnings.append(f"Skipped cue {cue.id}; start time is beyond the chapter length.")
                continue
            cue_samples = self._cue_samples(asset, target_length - start_frame, cue)
            if cue_samples.size == 0:
                continue
            # Vectorised placement: gain x equal-power fade envelope x ramped duck curve,
            # summed into the stem at the cue's start frame (no per-sample Python loop).
            contribution = (
                cue_samples
                * self._cue_gain(cue, render_mode)
                * self._cue_envelope(cue_samples.size, cue)
                * self._duck_curve(cue_samples.size, cue)
            )
            end = min(target_length, start_frame + contribution.size)
            stem[start_frame:end] += contribution[: end - start_frame]
        self._write_array(stem_path, self._limit_to_pcm16(stem))
        self._write_array(mixed_path, self._limit_to_pcm16(speech + stem))
        return warnings

    def _cue_samples(
        self, asset: np.ndarray, max_frames: int, cue: SoundCueInput
    ) -> np.ndarray:
        if max_frames <= 0:
            return asset[:0]
        if cue.asset_type in {"ambience", "music"} or cue.cue_type in {"ambience", "music"}:
            xfade_frames = int(self.sample_rate * AMBIENCE_CROSSFADE_MS / 1000)
            return self._tile_with_crossfade(asset, max_frames, xfade_frames)
        return asset[:max_frames]

    @staticmethod
    def _tile_with_crossfade(asset: np.ndarray, total: int, xfade_frames: int) -> np.ndarray:
        """Loop ``asset`` to ``total`` frames with a 250 ms equal-power crossfade per seam.

        Each copy's leading/trailing ``xfade`` frames are windowed by ``sqrt`` ramps so
        that a copy's fade-out overlaps the next copy's fade-in with unit power -- no
        click, no level bump at the loop boundary. The very first head and very last tail
        keep their full level (the cue's own fade in/out shapes those).
        """
        length = asset.size
        if length == 0 or total <= 0:
            return asset[:0]
        xfade = int(min(xfade_frames, length // 2))
        if xfade <= 0 or length >= total:
            reps = int(np.ceil(total / length))
            return np.tile(asset, reps)[:total]
        hop = length - xfade
        n_copies = int(np.ceil((total - length) / hop)) + 1
        out = np.zeros(hop * (n_copies - 1) + length, dtype=np.float64)
        fade_in = np.sqrt(np.linspace(0.0, 1.0, xfade, endpoint=False))
        fade_out = np.sqrt(np.linspace(1.0, 0.0, xfade, endpoint=False))
        for index in range(n_copies):
            copy = asset.astype(np.float64).copy()
            if index > 0:
                copy[:xfade] *= fade_in
            if index < n_copies - 1:
                copy[-xfade:] *= fade_out
            start = index * hop
            out[start : start + length] += copy
        return out[:total]

    def _cue_envelope(self, count: int, cue: SoundCueInput) -> np.ndarray:
        envelope = np.ones(count, dtype=np.float64)
        fade_in = min(int(self.sample_rate * max(0, cue.fade_in_ms) / 1000), count)
        fade_out = min(int(self.sample_rate * max(0, cue.fade_out_ms) / 1000), count)
        if fade_in > 0:
            envelope[:fade_in] = np.sqrt(np.linspace(0.0, 1.0, fade_in, endpoint=False))
        if fade_out > 0:
            envelope[count - fade_out :] = np.minimum(
                envelope[count - fade_out :],
                np.sqrt(np.linspace(1.0, 0.0, fade_out, endpoint=False)),
            )
        return envelope

    def _duck_curve(self, count: int, cue: SoundCueInput) -> np.ndarray:
        """Static -6 dB duck applied with 50 ms ramps so the level change never zips."""
        if not cue.ducking or count == 0:
            return np.ones(count, dtype=np.float64)
        ducked = 10 ** (DUCK_ATTENUATION_DB / 20)
        curve = np.full(count, ducked, dtype=np.float64)
        ramp = min(int(self.sample_rate * DUCK_RAMP_MS / 1000), count // 2)
        if ramp > 0:
            curve[:ramp] = np.linspace(1.0, ducked, ramp, endpoint=False)
            curve[count - ramp :] = np.linspace(ducked, 1.0, ramp)
        return curve

    @staticmethod
    def _cue_gain(cue: SoundCueInput, render_mode: str) -> float:
        if render_mode == "light_cinematic":
            maximum = -14.0 if cue.asset_type == "sfx" or cue.cue_type == "sfx" else -18.0
        else:
            maximum = -10.0 if cue.asset_type == "sfx" or cue.cue_type == "sfx" else -14.0
        gain_db = min(cue.gain_db, maximum)
        return 10 ** (gain_db / 20)

    @staticmethod
    def _limit_to_pcm16(samples: np.ndarray) -> np.ndarray:
        """Fold a float mix bus down to PCM16, soft-limiting only when it would clip."""
        if samples.size == 0:
            return np.zeros(0, dtype=np.int16)
        ceiling = mastering.FULL_SCALE - 1.0
        peak = float(np.max(np.abs(samples)))
        if peak > ceiling:
            # tanh knee rounds transients over the ceiling instead of squaring them off;
            # ffmpeg's alimiter does the real true-peak limiting at the mastering stage.
            samples = np.tanh(samples / ceiling) * ceiling
        return np.clip(np.round(samples), -32_768, 32_767).astype(np.int16)

    def _read_samples_array(self, path: Path) -> np.ndarray:
        """Decode a WAV to mono int16 samples at the assembler's 44.1 kHz target rate."""
        with wave.open(str(path), "rb") as source:
            frames = source.readframes(source.getnframes())
            width = source.getsampwidth()
            channels = source.getnchannels()
            rate = source.getframerate()
        if channels < 1:
            raise ValueError(f"Unsupported channel count in {path}: {channels}.")
        if width not in {1, 2, 3, 4}:
            raise ValueError(f"Unsupported sample width in {path}: {width}.")
        if not frames:
            return np.zeros(0, dtype=np.int16)
        mono = self._decode_mono(frames, width, channels)
        if rate != self.sample_rate:
            mono = band_limited_resample(mono, rate, self.sample_rate)
        return np.clip(np.round(mono), -32_768, 32_767).astype(np.int16)

    @staticmethod
    def _decode_mono(frames: bytes, width: int, channels: int) -> np.ndarray:
        # Reuse audio_analysis's shared PCM decoder (1/2/3/4-byte widths -> 16-bit range).
        flat = _decode_pcm(frames, width).astype(np.float64)
        if channels > 1:
            usable = (flat.size // channels) * channels
            return flat[:usable].reshape(-1, channels).mean(axis=1)
        return flat

    def _normalized_frames(self, path: Path) -> bytes:
        return self._read_samples_array(path).tobytes()

    def _write_array(self, path: Path, samples: np.ndarray) -> None:
        with wave.open(str(path), "wb") as target:
            target.setnchannels(self.channels)
            target.setsampwidth(self.sample_width)
            target.setframerate(self.sample_rate)
            target.writeframes(np.ascontiguousarray(samples, dtype="<i2").tobytes())

    def _apply_mastering(self, output_path: Path) -> tuple[bool, dict[str, str] | None]:
        """Room-tone + master ``output_path`` in place; return (mastered, measured stats).

        Room tone is always laid down (numpy, no ffmpeg). When ffmpeg is present the
        room-toned bed is loudness-normalised (-19 LUFS, linear) and true-peak-limited
        (-3 dBTP), and the final measured loudness is returned. When ffmpeg is missing --
        or the master pass fails -- the un-mastered 44.1 kHz bed is written and
        ``mastered`` is False so callers can degrade honestly.
        """
        core = self._read_samples_array(output_path)
        head = mastering.room_tone(mastering.ROOM_TONE_HEAD_MS, self.sample_rate)
        tail = mastering.room_tone(mastering.ROOM_TONE_TAIL_MS, self.sample_rate)
        combined = np.concatenate([head, core, tail]).astype(np.int16)
        if not mastering.ffmpeg_available():
            self._write_array(output_path, combined)
            return False, None
        premaster = output_path.with_name(f"{output_path.stem}.premaster.wav")
        try:
            self._write_array(premaster, combined)
            measured = mastering.measure_loudness(premaster)
            mastering.master_wav(premaster, output_path, measured)
            final = mastering.measure_loudness(output_path)
            return True, final
        except (ValueError, OSError, wave.Error):
            self._write_array(output_path, combined)
            return False, None
        finally:
            premaster.unlink(missing_ok=True)

    @staticmethod
    def _mastering_measurement(measured: dict[str, str] | None) -> dict[str, float]:
        if not measured:
            return {}
        summary: dict[str, float] = {}
        for source_key, target_key in (
            ("input_i", "integratedLufs"),
            ("input_tp", "truePeakDb"),
            ("input_lra", "lra"),
        ):
            try:
                summary[target_key] = float(measured[source_key])
            except (KeyError, ValueError):
                continue
        return summary

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
    def _int_manifest_value(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        return int(value)

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
