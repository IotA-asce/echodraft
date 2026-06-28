import json
import hashlib
import shutil
import subprocess
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import uuid4

from echodraft_db.models import ChapterRecord, SceneRecord, SegmentRecord
from echodraft_domain import DirectionProfile, SegmentDirection, VoicePreview
from sqlalchemy import select

from .container import AppContainer

CONTROLLED_EMOTIONS = {
    "neutral",
    "warm",
    "tense",
    "quiet",
    "urgent",
    "somber",
    "bright",
    "fearful",
    "angry",
}


class TtsAdapter(ABC):
    @abstractmethod
    def list_voices(self) -> list[str]: ...
    @abstractmethod
    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]: ...


class MockTtsAdapter(TtsAdapter):
    def list_voices(self) -> list[str]:
        return ["mock-narrator", "mock-character"]

    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]:
        frames = b"\x00\x00" * max(8000, min(48000, len(text) * 100))
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(frames)
        return {
            "provider": "mock",
            "modelVersion": "mock-0.1",
            "voiceId": voice_id,
            "effectiveDirection": direction.model_dump(by_alias=True),
        }


class KokoroTtsAdapter(TtsAdapter):
    def __init__(
        self, executable: str | None, model_path: Path | None, voice_path: Path | None
    ) -> None:
        self.executable, self.model_path, self.voice_path = executable, model_path, voice_path

    def readiness(self) -> str | None:
        if not self.executable or not shutil.which(self.executable):
            return "Kokoro executable is not available. Set ECHODRAFT_KOKORO_EXECUTABLE."
        if not self.model_path or not self.model_path.is_file():
            return "Kokoro model is missing. Set ECHODRAFT_KOKORO_MODEL_PATH."
        if not self.voice_path or not self.voice_path.is_file():
            return "Kokoro voice registry is missing. Set ECHODRAFT_KOKORO_VOICE_PATH."
        return None

    def list_voices(self) -> list[str]:
        if self.readiness():
            return []
        assert self.voice_path is not None
        return [
            line.strip()
            for line in self.voice_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]:
        if error := self.readiness():
            raise ValueError(error)
        assert self.executable is not None
        assert self.model_path is not None
        assert self.voice_path is not None
        if voice_id not in self.list_voices():
            raise ValueError(f"Kokoro voice '{voice_id}' is not registered locally.")
        command = [
            self.executable,
            "--model",
            str(self.model_path),
            "--voices",
            str(self.voice_path),
            "--voice",
            voice_id,
            "--text",
            text,
            "--output",
            str(output),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
        if completed.returncode:
            raise ValueError(
                f"Kokoro synthesis failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            with wave.open(str(output), "rb") as audio:
                if audio.getnframes() == 0:
                    raise ValueError("Kokoro returned an empty WAV file.")
                sample_rate = audio.getframerate()
        except wave.Error as wave_error:
            raise ValueError(f"Kokoro produced malformed WAV output: {wave_error}") from wave_error
        return {
            "provider": "kokoro",
            "modelVersion": hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16],
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "effectiveDirection": {"pace": direction.pace},
            "unsupportedDirection": [
                "intensity",
                "tone",
                "emotion",
                "pauseBeforeMs",
                "pauseAfterMs",
                "emphasis",
                "whisper",
            ],
        }


class ManagedKokoroOnnxAdapter(TtsAdapter):
    def __init__(
        self,
        python_path: Path | None,
        wrapper_path: Path | None,
        model_path: Path | None,
        voices_data_path: Path | None,
        voice_registry_path: Path | None,
    ) -> None:
        self.python_path = python_path
        self.wrapper_path = wrapper_path
        self.model_path = model_path
        self.voices_data_path = voices_data_path
        self.voice_registry_path = voice_registry_path

    def readiness(self) -> str | None:
        if not self.python_path or not self.python_path.is_file():
            return "Kokoro setup is incomplete. Open Voice setup and run Set up Kokoro voice system."
        if not self.wrapper_path or not self.wrapper_path.is_file():
            return "Kokoro setup is missing its local helper. Run Repair setup from Voice setup."
        if not self.model_path or not self.model_path.is_file():
            return "Kokoro model is missing. Run Repair setup from Voice setup."
        if not self.voices_data_path or not self.voices_data_path.is_file():
            return "Kokoro voice data is missing. Run Repair setup from Voice setup."
        if not self.voice_registry_path or not self.voice_registry_path.is_file():
            return "Kokoro voice list is missing. Run Repair setup from Voice setup."
        return None

    def list_voices(self) -> list[str]:
        if self.readiness():
            return []
        assert self.voice_registry_path is not None
        return [
            line.strip()
            for line in self.voice_registry_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]:
        if error := self.readiness():
            raise ValueError(error)
        assert self.python_path is not None
        assert self.wrapper_path is not None
        assert self.model_path is not None
        assert self.voices_data_path is not None
        assert self.voice_registry_path is not None
        if voice_id not in self.list_voices():
            raise ValueError(f"Kokoro voice '{voice_id}' is not registered locally.")
        command = [
            str(self.python_path),
            str(self.wrapper_path),
            "--model",
            str(self.model_path),
            "--voices-data",
            str(self.voices_data_path),
            "--voice-registry",
            str(self.voice_registry_path),
            "--voice",
            voice_id,
            "--text",
            text,
            "--output",
            str(output),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180, check=False
        )
        if completed.returncode:
            raise ValueError(
                f"Kokoro synthesis failed: {completed.stderr.strip() or completed.stdout.strip()}"
            )
        try:
            with wave.open(str(output), "rb") as audio:
                if audio.getnframes() == 0:
                    raise ValueError("Kokoro returned an empty WAV file.")
                sample_rate = audio.getframerate()
        except wave.Error as wave_error:
            raise ValueError(f"Kokoro produced malformed WAV output: {wave_error}") from wave_error
        return {
            "provider": "kokoro",
            "setupMode": "managed_onnx",
            "modelVersion": hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16],
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "effectiveDirection": {"pace": direction.pace},
            "unsupportedDirection": [
                "intensity",
                "tone",
                "emotion",
                "pauseBeforeMs",
                "pauseAfterMs",
                "emphasis",
                "whisper",
            ],
        }


class DirectionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.adapter = container.tts_adapter

    def preview(
        self, project_id: str, text: str, voice_id: str, direction: DirectionProfile
    ) -> VoicePreview:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        path = (
            Path(project.artifact_path) / "audio" / "previews" / f"preview_{uuid4().hex[:12]}.wav"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        profile = self.container.casting.voice(voice_id)
        provider_voice_id = profile.provider_voice_id if profile and profile.provider_voice_id else voice_id
        metadata = self.adapter.preview(text, provider_voice_id, path, direction)
        manifest = Path(project.artifact_path) / "manifests" / "direction_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "manifestType": "direction_manifest",
                    "schemaVersion": "0.1.0",
                    "projectId": project_id,
                    "payload": {
                        "voiceProfileId": voice_id,
                        "effectiveDirection": direction.model_dump(by_alias=True),
                        "tts": metadata,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return VoicePreview(
            assetPath=str(path),
            adapter=str(metadata["provider"]),
            modelVersion=str(metadata["modelVersion"]),
            direction=direction,
        )

    def list_segment_directions(self, project_id: str) -> list[SegmentDirection]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        return self.container.segment_directions.all_for_project(project_id)

    def segment_direction(self, project_id: str, segment_id: str) -> SegmentDirection:
        self._validate_segment_project(project_id, segment_id)
        existing = self.container.segment_directions.get(segment_id)
        if existing:
            return existing
        direction = DirectionProfile(scopeType="segment", scopeId=segment_id)
        return self._save(project_id, segment_id, direction, "manual", False)

    def update_segment_direction(
        self, project_id: str, segment_id: str, direction: DirectionProfile, user_locked: bool
    ) -> SegmentDirection:
        self._validate_segment_project(project_id, segment_id)
        return self._save(project_id, segment_id, direction, "manual", user_locked)

    def infer_segment_directions(self, project_id: str, job_id: str | None = None) -> list[SegmentDirection]:
        if not self.container.projects.get(project_id):
            raise ValueError("Project not found.")
        segments = self._segments(project_id)
        for index, segment in enumerate(segments, 1):
            self._save(project_id, segment.id, self._infer(segment), "inferred", False)
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id,
                    {
                        "phase": "direction_inference",
                        "current": index,
                        "total": len(segments),
                        "segmentId": segment.id,
                    },
                )
        return self.list_segment_directions(project_id)

    def _save(
        self,
        project_id: str,
        segment_id: str,
        direction: DirectionProfile,
        source: str,
        user_locked: bool,
    ) -> SegmentDirection:
        normalized = self._normalized(direction, segment_id)
        payload = json.dumps(normalized.model_dump(by_alias=True), sort_keys=True)
        return self.container.segment_directions.upsert(
            project_id,
            segment_id,
            payload,
            source,
            user_locked,
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _normalized(direction: DirectionProfile, segment_id: str) -> DirectionProfile:
        if direction.emotion not in CONTROLLED_EMOTIONS:
            raise ValueError(
                f"Emotion must be one of: {', '.join(sorted(CONTROLLED_EMOTIONS))}."
            )
        return direction.model_copy(update={"scope_type": "segment", "scope_id": segment_id})

    @staticmethod
    def _infer(segment: SegmentRecord) -> DirectionProfile:
        text = segment.text_content.casefold()
        emotion = "neutral"
        intensity = 0.42
        pace = 1.0
        whisper = False
        pause_after = 120
        if any(token in text for token in ("whisper", "softly", "hushed")):
            emotion = "quiet"
            intensity = 0.25
            pace = 0.88
            whisper = True
        elif "!" in segment.text_content or any(token in text for token in ("run", "hurry", "now")):
            emotion = "urgent"
            intensity = 0.72
            pace = 1.12
            pause_after = 80
        elif "?" in segment.text_content:
            emotion = "tense"
            intensity = 0.56
        elif any(token in text for token in ("grief", "alone", "rain", "grave")):
            emotion = "somber"
            intensity = 0.35
            pace = 0.92
            pause_after = 220
        return DirectionProfile(
            scopeType="segment",
            scopeId=segment.id,
            pace=pace,
            intensity=intensity,
            tone=emotion,
            emotion=emotion,
            pauseAfterMs=pause_after,
            whisper=whisper,
            stylePrompt=f"{emotion} audiobook delivery",
        )

    def _validate_segment_project(self, project_id: str, segment_id: str) -> None:
        segment = self.container.structure.segment(segment_id)
        if not segment:
            raise ValueError("Segment not found.")
        with self.container.structure.database.session() as session:
            scene = session.get(SceneRecord, segment.scene_id)
            chapter = session.get(ChapterRecord, scene.chapter_id) if scene else None
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Segment or project not found.")

    def _segments(self, project_id: str) -> list[SegmentRecord]:
        with self.container.structure.database.session() as session:
            return list(
                session.scalars(
                    select(SegmentRecord)
                    .join(SceneRecord, SegmentRecord.scene_id == SceneRecord.id)
                    .join(ChapterRecord, SceneRecord.chapter_id == ChapterRecord.id)
                    .where(ChapterRecord.project_id == project_id)
                    .order_by(
                        ChapterRecord.order_index,
                        SceneRecord.order_index,
                        SegmentRecord.order_index,
                    )
                )
            )
