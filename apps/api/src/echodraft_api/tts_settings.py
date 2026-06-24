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
        self.fallback = TtsSettingsUpdate(
            provider=settings.tts_provider,
            executable=settings.kokoro_executable,
            modelPath=str(settings.kokoro_model_path) if settings.kokoro_model_path else None,
            voiceRegistryPath=str(settings.kokoro_voice_path) if settings.kokoro_voice_path else None,
        )

    def load(self) -> TtsSettingsUpdate:
        if not self.path.is_file():
            return self.fallback
        return TtsSettingsUpdate.model_validate(json.loads(self.path.read_text(encoding="utf-8")))

    def adapter(self, payload: TtsSettingsUpdate | None = None) -> "TtsAdapter":
        config = payload or self.load()
        from .direction import KokoroTtsAdapter, MockTtsAdapter

        if config.provider == "mock":
            return MockTtsAdapter()
        return KokoroTtsAdapter(
            config.executable,
            Path(config.model_path).expanduser() if config.model_path else None,
            Path(config.voice_registry_path).expanduser() if config.voice_registry_path else None,
        )

    def status(self, payload: TtsSettingsUpdate | None = None) -> TtsSettings:
        config = payload or self.load()
        adapter = self.adapter(config)
        from .direction import KokoroTtsAdapter
        message = adapter.readiness() if isinstance(adapter, KokoroTtsAdapter) else None
        return TtsSettings(
            **config.model_dump(by_alias=True),
            ready=message is None,
            message=message,
            availableVoices=adapter.list_voices() if message is None else [],
        )

    def save(self, payload: TtsSettingsUpdate) -> TtsSettings:
        if payload.provider not in {"mock", "kokoro"}:
            raise ValueError("Supported TTS providers are mock and kokoro.")
        status = self.status(payload)
        if not status.ready:
            raise ValueError(status.message or "TTS provider is not ready.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload.model_dump(by_alias=True), indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return status
