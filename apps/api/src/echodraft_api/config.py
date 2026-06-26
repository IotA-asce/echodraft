import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    database_url: str
    artifact_root: Path
    tts_provider: str = "mock"
    kokoro_executable: str | None = None
    kokoro_model_path: Path | None = None
    kokoro_voices_data_path: Path | None = None
    kokoro_voice_path: Path | None = None
    kokoro_runtime_root: Path = Path(".echodraft/kokoro/managed-onnx-v1")
    tts_settings_path: Path = Path(".echodraft/tts-settings.json")

    @classmethod
    def from_environment(cls) -> "AppSettings":
        return cls(
            database_url=os.getenv("ECHODRAFT_DATABASE_URL", "sqlite:///./.echodraft/echodraft.db"),
            artifact_root=Path(
                os.getenv("ECHODRAFT_ARTIFACT_ROOT", ".echodraft/projects")
            ).resolve(),
            tts_provider=os.getenv("ECHODRAFT_TTS_PROVIDER", "mock").lower(),
            kokoro_executable=os.getenv("ECHODRAFT_KOKORO_EXECUTABLE"),
            kokoro_model_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_KOKORO_MODEL_PATH"))
                else None
            ),
            kokoro_voices_data_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_KOKORO_VOICES_DATA_PATH"))
                else None
            ),
            kokoro_voice_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_KOKORO_VOICE_PATH"))
                else None
            ),
            kokoro_runtime_root=Path(
                os.getenv("ECHODRAFT_KOKORO_RUNTIME_ROOT", ".echodraft/kokoro/managed-onnx-v1")
            ).expanduser().resolve(),
            tts_settings_path=Path(
                os.getenv("ECHODRAFT_TTS_SETTINGS_PATH", ".echodraft/tts-settings.json")
            ).expanduser().resolve(),
        )
