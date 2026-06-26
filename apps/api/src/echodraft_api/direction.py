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
