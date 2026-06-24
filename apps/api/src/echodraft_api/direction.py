import json
import hashlib
import shutil
import subprocess
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import uuid4

from echodraft_domain import DirectionProfile, VoicePreview

from .container import AppContainer


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
            "unsupportedDirection": ["intensity", "tone", "emphasis", "whisper"],
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
        metadata = self.adapter.preview(text, voice_id, path, direction)
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
