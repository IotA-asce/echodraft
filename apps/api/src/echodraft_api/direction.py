import json
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
    ) -> None: ...


class MockTtsAdapter(TtsAdapter):
    def list_voices(self) -> list[str]:
        return ["mock-narrator", "mock-character"]

    def preview(self, text: str, voice_id: str, output: Path, direction: DirectionProfile) -> None:
        frames = b"\x00\x00" * max(8000, min(48000, len(text) * 100))
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(frames)


class DirectionService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.adapter = MockTtsAdapter()

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
        self.adapter.preview(text, voice_id, path, direction)
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
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return VoicePreview(
            assetPath=str(path), adapter="mock", modelVersion="mock-0.1", direction=direction
        )
