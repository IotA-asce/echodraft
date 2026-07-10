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
    llm_worker_override: int | None = None
    subprocess_worker_override: int | None = None
    tts_worker_override: int | None = None
    audiogen_worker_override: int | None = None
    model_vram_budget_gib: float | None = None
    structure_v2_enabled: bool = False
    cast_v2_enabled: bool = False
    attribution_v2_enabled: bool = False
    confidence_v2_enabled: bool = False
    direction_v2_enabled: bool = False
    progressive_delivery_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "AppSettings":
        llm_worker_override = os.getenv("ECHODRAFT_LLM_WORKERS")
        subprocess_worker_override = os.getenv("ECHODRAFT_SUBPROCESS_WORKERS")
        tts_worker_override = os.getenv("ECHODRAFT_TTS_WORKERS")
        audiogen_worker_override = os.getenv("ECHODRAFT_AUDIOGEN_WORKERS")
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
            llm_worker_override=(
                int(llm_worker_override)
                if llm_worker_override and llm_worker_override.isdigit()
                else None
            ),
            subprocess_worker_override=_optional_positive_int(subprocess_worker_override),
            tts_worker_override=_optional_positive_int(tts_worker_override),
            audiogen_worker_override=_optional_positive_int(audiogen_worker_override),
            model_vram_budget_gib=_optional_positive_float(
                os.getenv("ECHODRAFT_MODEL_VRAM_BUDGET_GIB")
            ),
            structure_v2_enabled=_env_truthy("ECHODRAFT_STRUCTURE_V2_ENABLED")
            or _env_truthy("ECHODRAFT_STRUCTURE_V2"),
            cast_v2_enabled=_env_truthy("ECHODRAFT_CAST_V2_ENABLED")
            or _env_truthy("ECHODRAFT_CAST_V2"),
            attribution_v2_enabled=_env_truthy("ECHODRAFT_ATTRIBUTION_V2_ENABLED")
            or _env_truthy("ECHODRAFT_ATTRIBUTION_V2"),
            confidence_v2_enabled=_env_truthy("ECHODRAFT_CONFIDENCE_V2_ENABLED")
            or _env_truthy("ECHODRAFT_CONFIDENCE_V2"),
            direction_v2_enabled=_env_truthy("ECHODRAFT_DIRECTION_V2_ENABLED")
            or _env_truthy("ECHODRAFT_DIRECTION_V2"),
            progressive_delivery_enabled=_env_truthy(
                "ECHODRAFT_PROGRESSIVE_DELIVERY_ENABLED"
            )
            or _env_truthy("ECHODRAFT_PROGRESSIVE_DELIVERY"),
        )


def _optional_positive_int(value: str | None) -> int | None:
    if not value or not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _optional_positive_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}
