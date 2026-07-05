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
    piper_model_path: Path | None = None
    piper_config_path: Path | None = None
    xtts_reference_voice_path: Path | None = None
    xtts_reference_voice_consent: bool = False
    xtts_language: str = "en"
    asr_executable: str | None = None
    asr_model_path: Path | None = None
    local_ai_root: Path = Path(".echodraft/local-ai")
    ollama_base_url: str = "http://127.0.0.1:11434"
    tts_settings_path: Path = Path(".echodraft/tts-settings.json")
    max_concurrent_jobs: int = 2

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
            piper_model_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_PIPER_MODEL_PATH"))
                else None
            ),
            piper_config_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_PIPER_CONFIG_PATH"))
                else None
            ),
            xtts_reference_voice_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_XTTS_REFERENCE_VOICE_PATH"))
                else None
            ),
            xtts_reference_voice_consent=os.getenv(
                "ECHODRAFT_XTTS_REFERENCE_VOICE_CONSENT", ""
            ).lower()
            in {"1", "true", "yes"},
            xtts_language=os.getenv("ECHODRAFT_XTTS_LANGUAGE", "en"),
            asr_executable=os.getenv("ECHODRAFT_ASR_EXECUTABLE"),
            asr_model_path=(
                Path(value).expanduser().resolve()
                if (value := os.getenv("ECHODRAFT_ASR_MODEL_PATH"))
                else None
            ),
            local_ai_root=Path(
                os.getenv("ECHODRAFT_LOCAL_AI_ROOT", ".echodraft/local-ai")
            ).expanduser().resolve(),
            ollama_base_url=os.getenv("ECHODRAFT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            tts_settings_path=Path(
                os.getenv("ECHODRAFT_TTS_SETTINGS_PATH", ".echodraft/tts-settings.json")
            ).expanduser().resolve(),
            max_concurrent_jobs=int(os.getenv("ECHODRAFT_MAX_CONCURRENT_JOBS", "2")),
        )
