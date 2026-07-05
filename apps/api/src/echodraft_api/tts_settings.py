"""Durable, local-only TTS configuration."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from echodraft_domain import TtsSettings, TtsSettingsUpdate

from .config import AppSettings

if TYPE_CHECKING:
    from .tts_providers import TtsProvider
    from .tts_worker import TtsWorkerManager


class TtsSettingsStore:
    def __init__(self, settings: AppSettings) -> None:
        self.path = settings.tts_settings_path
        self.runtime_root = settings.kokoro_runtime_root
        self.fallback = TtsSettingsUpdate(
            provider=settings.tts_provider,
            setupMode="custom_adapter" if settings.tts_provider == "kokoro" else None,
            executable=settings.kokoro_executable,
            runtimeRoot=str(settings.kokoro_runtime_root),
            modelPath=str(settings.kokoro_model_path) if settings.kokoro_model_path else None,
            voicesDataPath=(
                str(settings.kokoro_voices_data_path) if settings.kokoro_voices_data_path else None
            ),
            voiceRegistryPath=str(settings.kokoro_voice_path) if settings.kokoro_voice_path else None,
            piperModelPath=str(settings.piper_model_path) if settings.piper_model_path else None,
            piperConfigPath=str(settings.piper_config_path) if settings.piper_config_path else None,
            referenceVoicePath=(
                str(settings.xtts_reference_voice_path)
                if settings.xtts_reference_voice_path
                else None
            ),
            referenceVoiceConsent=settings.xtts_reference_voice_consent,
            language=settings.xtts_language,
        )

    def load(self) -> TtsSettingsUpdate:
        if not self.path.is_file():
            return self._normalized(self.fallback)
        return self._normalized(
            TtsSettingsUpdate.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        )

    def adapter(
        self,
        payload: TtsSettingsUpdate | None = None,
        *,
        worker_manager: "TtsWorkerManager | None" = None,
    ) -> "TtsProvider":
        config = self._normalized(payload or self.load())
        from .tts_providers import (
            KokoroTtsAdapter,
            ManagedKokoroOnnxAdapter,
            MockTtsAdapter,
            PiperTtsAdapter,
            XttsV2Adapter,
        )

        if config.provider == "mock":
            return MockTtsAdapter()
        if config.provider == "piper":
            return PiperTtsAdapter(
                config.executable,
                Path(config.piper_model_path).expanduser() if config.piper_model_path else None,
                Path(config.piper_config_path).expanduser() if config.piper_config_path else None,
                Path(config.voice_registry_path).expanduser()
                if config.voice_registry_path
                else None,
            )
        if config.provider == "xtts_v2":
            return XttsV2Adapter(
                Path(config.python_path).expanduser() if config.python_path else None,
                Path(config.reference_voice_path).expanduser()
                if config.reference_voice_path
                else None,
                config.reference_voice_consent,
                config.language,
            )
        if config.setup_mode == "managed_onnx":
            return ManagedKokoroOnnxAdapter(
                Path(config.python_path).expanduser() if config.python_path else None,
                Path(config.executable).expanduser() if config.executable else None,
                Path(config.model_path).expanduser() if config.model_path else None,
                Path(config.voices_data_path).expanduser() if config.voices_data_path else None,
                Path(config.voice_registry_path).expanduser() if config.voice_registry_path else None,
                worker_manager,
            )
        return KokoroTtsAdapter(
            config.executable,
            Path(config.model_path).expanduser() if config.model_path else None,
            Path(config.voice_registry_path).expanduser() if config.voice_registry_path else None,
        )

    def status(self, payload: TtsSettingsUpdate | None = None) -> TtsSettings:
        config = payload or self.load()
        adapter = self.adapter(config)
        message = adapter.readiness()
        return TtsSettings(
            **config.model_dump(by_alias=True),
            ready=message is None,
            message=message,
            availableVoices=adapter.list_voices() if message is None else [],
        )

    def providers(self) -> list[dict[str, object]]:
        saved = self.load()
        candidates = [
            saved.model_copy(update={"provider": "mock"}),
            saved.model_copy(update={"provider": "kokoro"}),
            saved.model_copy(update={"provider": "piper"}),
            saved.model_copy(update={"provider": "xtts_v2"}),
        ]
        return [self.adapter(candidate).capability() for candidate in candidates]

    def save(self, payload: TtsSettingsUpdate) -> TtsSettings:
        payload = self._normalized(payload)
        if payload.provider not in {"mock", "kokoro", "piper", "xtts_v2"}:
            raise ValueError("Supported TTS providers are mock, kokoro, piper, and xtts_v2.")
        if payload.provider == "xtts_v2" and not payload.reference_voice_consent:
            raise ValueError("XTTS-v2 requires explicit consent for the local reference voice.")
        if payload.provider == "kokoro" and payload.setup_mode and payload.setup_mode not in {"managed_onnx", "custom_adapter"}:
            raise ValueError("Supported Kokoro setup modes are managed_onnx and custom_adapter.")
        status = self.status(payload)
        if not status.ready:
            raise ValueError(status.message or "TTS provider is not ready.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload.model_dump(by_alias=True), indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return status

    def _normalized(self, config: TtsSettingsUpdate) -> TtsSettingsUpdate:
        if config.provider == "mock":
            return config.model_copy(
                update={
                    "setup_mode": None,
                    "executable": None,
                    "runtime_root": None,
                    "python_path": None,
                    "model_path": None,
                    "voices_data_path": None,
                    "voice_registry_path": None,
                    "piper_model_path": None,
                    "piper_config_path": None,
                    "reference_voice_path": None,
                    "reference_voice_consent": False,
                }
            )
        if config.provider == "piper":
            return config.model_copy(
                update={
                    "setup_mode": "local_cli",
                    "runtime_root": None,
                    "python_path": None,
                    "model_path": None,
                    "voices_data_path": None,
                    "reference_voice_path": None,
                    "reference_voice_consent": False,
                }
            )
        if config.provider == "xtts_v2":
            return config.model_copy(
                update={
                    "setup_mode": "coqui_local",
                    "executable": None,
                    "runtime_root": None,
                    "model_path": None,
                    "voices_data_path": None,
                    "voice_registry_path": None,
                    "piper_model_path": None,
                    "piper_config_path": None,
                    "language": config.language or "en",
                }
            )
        setup_mode = config.setup_mode
        if setup_mode not in {"managed_onnx", "custom_adapter"}:
            setup_mode = None
        if not setup_mode:
            setup_mode = "managed_onnx" if config.python_path or config.voices_data_path else "custom_adapter"
        return config.model_copy(
            update={
                "setup_mode": setup_mode,
                "runtime_root": config.runtime_root or str(self.runtime_root),
            }
        )
