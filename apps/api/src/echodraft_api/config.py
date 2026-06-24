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
    kokoro_voice_path: Path | None = None

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
            kokoro_voice_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_KOKORO_VOICE_PATH"))
                else None
            ),
        )
