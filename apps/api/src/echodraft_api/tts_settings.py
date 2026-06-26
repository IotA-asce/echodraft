"""Durable, local-only TTS configuration."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from echodraft_domain import TtsSettings, TtsSettingsUpdate

from .config import AppSettings

if TYPE_CHECKING:
    from .direction import TtsAdapter


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
        )

    def load(self) -> TtsSettingsUpdate:
        if not self.path.is_file():
            return self._normalized(self.fallback)
        return self._normalized(
            TtsSettingsUpdate.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        )

    def adapter(self, payload: TtsSettingsUpdate | None = None) -> "TtsAdapter":
        config = self._normalized(payload or self.load())
        from .direction import KokoroTtsAdapter, ManagedKokoroOnnxAdapter, MockTtsAdapter

        if config.provider == "mock":
            return MockTtsAdapter()
        if config.setup_mode == "managed_onnx":
            return ManagedKokoroOnnxAdapter(
                Path(config.python_path).expanduser() if config.python_path else None,
                Path(config.executable).expanduser() if config.executable else None,
                Path(config.model_path).expanduser() if config.model_path else None,
                Path(config.voices_data_path).expanduser() if config.voices_data_path else None,
                Path(config.voice_registry_path).expanduser() if config.voice_registry_path else None,
            )
        return KokoroTtsAdapter(
            config.executable,
            Path(config.model_path).expanduser() if config.model_path else None,
            Path(config.voice_registry_path).expanduser() if config.voice_registry_path else None,
        )

    def status(self, payload: TtsSettingsUpdate | None = None) -> TtsSettings:
        config = payload or self.load()
        adapter = self.adapter(config)
        from .direction import KokoroTtsAdapter, ManagedKokoroOnnxAdapter
        message = (
            adapter.readiness()
            if isinstance(adapter, (KokoroTtsAdapter, ManagedKokoroOnnxAdapter))
            else None
        )
        return TtsSettings(
            **config.model_dump(by_alias=True),
            ready=message is None,
            message=message,
            availableVoices=adapter.list_voices() if message is None else [],
        )

    def save(self, payload: TtsSettingsUpdate) -> TtsSettings:
        payload = self._normalized(payload)
        if payload.provider not in {"mock", "kokoro"}:
            raise ValueError("Supported TTS providers are mock and kokoro.")
        if payload.setup_mode and payload.setup_mode not in {"managed_onnx", "custom_adapter"}:
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
        if config.provider != "kokoro":
            return config.model_copy(
                update={
                    "setup_mode": None,
                    "executable": None,
                    "runtime_root": None,
                    "python_path": None,
                    "model_path": None,
                    "voices_data_path": None,
                    "voice_registry_path": None,
                }
            )
        setup_mode = config.setup_mode
        if not setup_mode:
            setup_mode = "managed_onnx" if config.python_path or config.voices_data_path else "custom_adapter"
        return config.model_copy(
            update={
                "setup_mode": setup_mode,
                "runtime_root": config.runtime_root or str(self.runtime_root),
            }
        )
