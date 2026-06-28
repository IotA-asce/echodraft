"""Local TTS provider contracts and adapters."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import wave
from abc import ABC, abstractmethod
from pathlib import Path

from echodraft_domain import DirectionProfile


class TtsProvider(ABC):
    provider_id = "unknown"
    display_name = "Unknown provider"
    setup_mode: str | None = None
    supports_reference_voice = False
    supports_pronunciation = False
    requires_reference_consent = False
    direction_support: set[str] = set()

    def readiness(self) -> str | None:
        return None

    def model_version(self) -> str:
        return "unknown"

    def capability(self) -> dict[str, object]:
        message = self.readiness()
        return {
            "provider": self.provider_id,
            "displayName": self.display_name,
            "setupMode": self.setup_mode,
            "ready": message is None,
            "message": message,
            "availableVoices": self.list_voices() if message is None else [],
            "capabilities": {
                "voicePreview": True,
                "pronunciation": self.supports_pronunciation,
                "referenceVoice": self.supports_reference_voice,
                "direction": sorted(self.direction_support),
            },
            "requiresReferenceConsent": self.requires_reference_consent,
        }

    def render_identity(self) -> dict[str, object]:
        return {
            "provider": self.provider_id,
            "setupMode": self.setup_mode,
            "modelVersion": self.model_version(),
        }

    @abstractmethod
    def list_voices(self) -> list[str]: ...

    @abstractmethod
    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]: ...


class MockTtsAdapter(TtsProvider):
    provider_id = "mock"
    display_name = "Mock workflow audio"
    supports_pronunciation = True
    direction_support = {
        "pace",
        "intensity",
        "tone",
        "emotion",
        "pauseBeforeMs",
        "pauseAfterMs",
        "emphasis",
        "whisper",
    }

    def model_version(self) -> str:
        return "mock-0.1"

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
            **self.render_identity(),
            "voiceId": voice_id,
            "effectiveDirection": direction.model_dump(by_alias=True),
        }


class KokoroTtsAdapter(TtsProvider):
    provider_id = "kokoro"
    display_name = "Kokoro custom adapter"
    setup_mode = "custom_adapter"
    direction_support = {"pace"}

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

    def model_version(self) -> str:
        if not self.model_path or not self.model_path.is_file():
            return "missing"
        return hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16]

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
        _run_tts_command(command, "Kokoro", timeout=120)
        sample_rate = _validate_wav(output, "Kokoro")
        return {
            **self.render_identity(),
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "effectiveDirection": {"pace": direction.pace},
            "unsupportedDirection": _unsupported_direction(self.direction_support),
        }


class ManagedKokoroOnnxAdapter(TtsProvider):
    provider_id = "kokoro"
    display_name = "Kokoro managed ONNX"
    setup_mode = "managed_onnx"
    direction_support = {"pace"}

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

    def model_version(self) -> str:
        if not self.model_path or not self.model_path.is_file():
            return "missing"
        return hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16]

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
        _run_tts_command(command, "Kokoro", timeout=180)
        sample_rate = _validate_wav(output, "Kokoro")
        return {
            **self.render_identity(),
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "effectiveDirection": {"pace": direction.pace},
            "unsupportedDirection": _unsupported_direction(self.direction_support),
        }


class PiperTtsAdapter(TtsProvider):
    provider_id = "piper"
    display_name = "Piper local CLI"
    setup_mode = "local_cli"
    supports_pronunciation = True
    direction_support = {"pace", "pauseAfterMs"}

    def __init__(
        self,
        executable: str | None,
        model_path: Path | None,
        config_path: Path | None,
        voice_registry_path: Path | None,
    ) -> None:
        self.executable = executable or "piper"
        self.model_path = model_path
        self.config_path = config_path
        self.voice_registry_path = voice_registry_path

    def readiness(self) -> str | None:
        if not self.executable or not shutil.which(self.executable):
            return "Piper executable is not available. Install Piper or set executable to its local CLI path."
        if not self.model_path or not self.model_path.is_file():
            return "Piper model is missing. Provide a local .onnx model path."
        if self.config_path and not self.config_path.is_file():
            return "Piper config path is set but the file does not exist."
        return None

    def model_version(self) -> str:
        if not self.model_path or not self.model_path.is_file():
            return "missing"
        return hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:16]

    def list_voices(self) -> list[str]:
        if self.readiness():
            return []
        if self.voice_registry_path and self.voice_registry_path.is_file():
            return [
                line.strip()
                for line in self.voice_registry_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
        assert self.model_path is not None
        return [self.model_path.stem]

    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]:
        if error := self.readiness():
            raise ValueError(error)
        assert self.executable is not None
        assert self.model_path is not None
        command = [self.executable, "-m", str(self.model_path), "-f", str(output)]
        if self.config_path:
            command.extend(["-c", str(self.config_path)])
        speaker_id = _piper_speaker_id(voice_id)
        if speaker_id is not None:
            command.extend(["-s", str(speaker_id)])
        command.extend(["--length-scale", f"{max(0.5, min(2.0, 1 / direction.pace)):.3f}"])
        if direction.pause_after_ms:
            command.extend(["--sentence-silence", f"{direction.pause_after_ms / 1000:.3f}"])
        _run_tts_command(command, "Piper", timeout=180, stdin=text)
        sample_rate = _validate_wav(output, "Piper")
        return {
            **self.render_identity(),
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "effectiveDirection": {
                "pace": direction.pace,
                "pauseAfterMs": direction.pause_after_ms,
            },
            "unsupportedDirection": _unsupported_direction(self.direction_support),
        }


class XttsV2Adapter(TtsProvider):
    provider_id = "xtts_v2"
    display_name = "XTTS-v2 local Coqui"
    setup_mode = "coqui_local"
    supports_reference_voice = True
    supports_pronunciation = True
    requires_reference_consent = True
    direction_support = {"stylePrompt"}

    def __init__(
        self,
        python_path: Path | None,
        reference_voice_path: Path | None,
        reference_voice_consent: bool,
        language: str,
    ) -> None:
        self.python_path = python_path
        self.reference_voice_path = reference_voice_path
        self.reference_voice_consent = reference_voice_consent
        self.language = language or "en"

    def readiness(self) -> str | None:
        if not self.reference_voice_consent:
            return "XTTS-v2 requires explicit consent for the local reference voice."
        if not self.reference_voice_path or not self.reference_voice_path.is_file():
            return "XTTS-v2 reference voice WAV is missing."
        if not self.python_path or not self.python_path.is_file():
            return "XTTS-v2 Python runtime is missing. Provide a local Python with Coqui TTS installed."
        return None

    def model_version(self) -> str:
        return "tts_models/multilingual/multi-dataset/xtts_v2"

    def capability(self) -> dict[str, object]:
        capability = super().capability()
        capability["referenceVoiceConsent"] = self.reference_voice_consent
        capability["referenceVoicePath"] = str(self.reference_voice_path) if self.reference_voice_path else None
        return capability

    def list_voices(self) -> list[str]:
        if self.readiness():
            return []
        assert self.reference_voice_path is not None
        return [self.reference_voice_path.stem]

    def preview(
        self, text: str, voice_id: str, output: Path, direction: DirectionProfile
    ) -> dict[str, object]:
        if error := self.readiness():
            raise ValueError(error)
        assert self.python_path is not None
        assert self.reference_voice_path is not None
        script = (
            "import sys\n"
            "from TTS.api import TTS\n"
            "tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', progress_bar=False, gpu=False)\n"
            "tts.tts_to_file(text=sys.argv[1], speaker_wav=sys.argv[2], "
            "language=sys.argv[3], file_path=sys.argv[4], split_sentences=True)\n"
        )
        command = [
            str(self.python_path),
            "-c",
            script,
            text,
            str(self.reference_voice_path),
            self.language,
            str(output),
        ]
        _run_tts_command(command, "XTTS-v2", timeout=420)
        sample_rate = _validate_wav(output, "XTTS-v2")
        return {
            **self.render_identity(),
            "voiceId": voice_id,
            "sampleRate": sample_rate,
            "referenceVoicePath": str(self.reference_voice_path),
            "language": self.language,
            "effectiveDirection": {"stylePrompt": direction.style_prompt},
            "unsupportedDirection": _unsupported_direction(self.direction_support),
        }


def _run_tts_command(
    command: list[str], provider_name: str, *, timeout: int, stdin: str | None = None
) -> None:
    completed = subprocess.run(
        command,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            f"{provider_name} synthesis failed: {completed.stderr.strip() or completed.stdout.strip()}"
        )


def _validate_wav(output: Path, provider_name: str) -> int:
    try:
        with wave.open(str(output), "rb") as audio:
            if audio.getnframes() == 0:
                raise ValueError(f"{provider_name} returned an empty WAV file.")
            return audio.getframerate()
    except wave.Error as wave_error:
        raise ValueError(f"{provider_name} produced malformed WAV output: {wave_error}") from wave_error


def _unsupported_direction(supported: set[str]) -> list[str]:
    all_controls = {
        "pace",
        "intensity",
        "tone",
        "emotion",
        "pauseBeforeMs",
        "pauseAfterMs",
        "emphasis",
        "whisper",
    }
    return sorted(all_controls - supported)


def _piper_speaker_id(voice_id: str) -> int | None:
    if voice_id.isdigit():
        return int(voice_id)
    if voice_id.startswith("speaker:") and voice_id.removeprefix("speaker:").isdigit():
        return int(voice_id.removeprefix("speaker:"))
    return None
