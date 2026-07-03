"""Managed local Kokoro ONNX setup."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import cast

from echodraft_db import JobRepository
from echodraft_domain import (
    DirectionProfile,
    KokoroSetupStatus,
    KokoroSetupStep,
    TtsSettingsUpdate,
)

from .config import AppSettings
from .tts_providers import ManagedKokoroOnnxAdapter
from .tts_settings import TtsSettingsStore

KOKORO_ONNX_VERSION = "0.4.7"
MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    "kokoro-v1.0.onnx"
)
VOICES_DATA_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    "voices-v1.0.bin"
)

PHASES: tuple[tuple[str, str], ...] = (
    ("checking_python", "Check local Python"),
    ("creating_runtime", "Create local Kokoro runtime"),
    ("installing_packages", "Install Kokoro ONNX packages"),
    ("downloading_model", "Download Kokoro model"),
    ("downloading_voice_data", "Download Kokoro voice data"),
    ("building_voice_registry", "Build voice list"),
    ("validating_preview", "Validate voice preview"),
    ("saving_settings", "Save Echodraft settings"),
    ("completed", "Kokoro voice system ready"),
)


@dataclass(frozen=True)
class ManagedKokoroPaths:
    root: Path

    @property
    def venv(self) -> Path:
        return self.root / "venv"

    @property
    def python(self) -> Path:
        return managed_python_path(self.root)

    @property
    def wrapper(self) -> Path:
        return self.root / "echodraft_kokoro_onnx"

    @property
    def model(self) -> Path:
        return self.root / "kokoro-v1.0.onnx"

    @property
    def voices_data(self) -> Path:
        return self.root / "voices-v1.0.bin"

    @property
    def voice_registry(self) -> Path:
        return self.root / "voices.txt"

    @property
    def probe(self) -> Path:
        return self.root / "setup-preview.wav"

    @property
    def state(self) -> Path:
        return self.root / "setup-state.json"


def managed_python_path(runtime_root: Path, platform_name: str | None = None) -> Path:
    system = platform_name or platform.system()
    if system == "Windows":
        return runtime_root / "venv" / "Scripts" / "python.exe"
    return runtime_root / "venv" / "bin" / "python"


class ManagedKokoroSetupService:
    def __init__(
        self,
        settings: AppSettings,
        tts_settings: TtsSettingsStore,
        jobs_repository: JobRepository,
    ) -> None:
        self.settings = settings
        self.tts_settings = tts_settings
        self.jobs_repository = jobs_repository
        self.paths = ManagedKokoroPaths(settings.kokoro_runtime_root)

    def status(self) -> KokoroSetupStatus:
        adapter = self._adapter()
        message = adapter.readiness()
        voices = adapter.list_voices() if message is None else []
        active = self.tts_settings.load()
        active_managed = active.provider == "kokoro" and active.setup_mode == "managed_onnx"
        saved_state = self._read_state()

        if saved_state.get("state") == "failed":
            state = "failed"
            display_message = str(saved_state.get("message") or message or "Kokoro setup failed.")
            next_action = "Select Repair setup after checking your network and disk space."
        elif message is None and voices:
            state = "active" if active_managed else "ready"
            next_action = (
                "Create a narrator from one of the available Kokoro voices."
                if active_managed
                else "Use this managed Kokoro runtime for voice setup."
            )
            display_message = "Kokoro voice system is ready."
        elif not self.paths.root.exists():
            state = "not_started"
            next_action = "Select Set up Kokoro voice system to install local Kokoro ONNX assets."
            display_message = "Kokoro has not been set up on this machine yet."
        else:
            state = "incomplete"
            display_message = message or "Kokoro setup is incomplete."
            next_action = "Select Repair setup to finish the local Kokoro installation."

        return KokoroSetupStatus(
            platform=platform.system() or os.name,
            state=state,
            setupMode="managed_onnx",
            runtimeRoot=str(self.paths.root),
            pythonPath=str(self.paths.python),
            executable=str(self.paths.wrapper),
            modelPath=str(self.paths.model),
            voicesDataPath=str(self.paths.voices_data),
            voiceRegistryPath=str(self.paths.voice_registry),
            ready=state in {"ready", "active"},
            message=display_message,
            nextAction=next_action,
            availableVoices=voices,
            steps=self._steps(state, message),
        )

    def install(self, job_id: str, repair: bool = False) -> TtsSettingsUpdate:
        try:
            payload = self._install(job_id, repair)
        except Exception as error:
            self._write_state("failed", str(error))
            raise
        self._write_state("ready", "Kokoro voice system is ready.")
        return payload

    def _install(self, job_id: str, repair: bool) -> TtsSettingsUpdate:
        self._progress(job_id, "checking_python", "Checking whether Python can create a local runtime.")
        if not sys.executable:
            raise ValueError("Python executable was not detected. Start Echodraft from a Python environment.")
        self._run([sys.executable, "-m", "venv", "--help"], "Python venv is unavailable", timeout=60)

        self._progress(job_id, "creating_runtime", "Creating an app-local Kokoro runtime.")
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self._write_wrapper()
        self._create_virtualenv()

        self._progress(job_id, "installing_packages", "Installing Kokoro ONNX into the local runtime.")
        self._install_packages()

        self._progress(job_id, "downloading_model", "Downloading Kokoro model weights.")
        self._download(MODEL_URL, self.paths.model, repair=repair)

        self._progress(job_id, "downloading_voice_data", "Downloading Kokoro voice data.")
        self._download(VOICES_DATA_URL, self.paths.voices_data, repair=repair)

        self._progress(job_id, "building_voice_registry", "Reading the Kokoro voice list.")
        voices = self._list_managed_voices()
        if not voices:
            raise ValueError("Kokoro installed, but no voices were reported by the local runtime.")
        self.paths.voice_registry.write_text(
            "# Echodraft managed Kokoro voice IDs\n" + "\n".join(voices) + "\n",
            encoding="utf-8",
        )

        payload = self._payload()
        self._progress(job_id, "validating_preview", "Synthesizing a short local preview.")
        self._validate_preview(payload, voices[0])

        self._progress(job_id, "saving_settings", "Saving Kokoro as the active Echodraft voice system.")
        self.tts_settings.save(payload)

        self._progress(job_id, "completed", "Kokoro voice system is ready.")
        return payload

    def _payload(self) -> TtsSettingsUpdate:
        return TtsSettingsUpdate(
            provider="kokoro",
            setupMode="managed_onnx",
            runtimeRoot=str(self.paths.root),
            pythonPath=str(self.paths.python),
            executable=str(self.paths.wrapper),
            modelPath=str(self.paths.model),
            voicesDataPath=str(self.paths.voices_data),
            voiceRegistryPath=str(self.paths.voice_registry),
        )

    def _adapter(self) -> ManagedKokoroOnnxAdapter:
        return ManagedKokoroOnnxAdapter(
            self.paths.python,
            self.paths.wrapper,
            self.paths.model,
            self.paths.voices_data,
            self.paths.voice_registry,
        )

    def _create_virtualenv(self) -> None:
        if self.paths.python.is_file():
            return
        self._run(
            [sys.executable, "-m", "venv", str(self.paths.venv)],
            "Could not create the local Kokoro Python runtime",
            timeout=180,
        )
        if not self.paths.python.is_file():
            raise ValueError("Local Kokoro Python runtime was not created successfully.")

    def _install_packages(self) -> None:
        self._run(
            [
                str(self.paths.python),
                "-m",
                "pip",
                "install",
                f"kokoro-onnx=={KOKORO_ONNX_VERSION}",
                "soundfile",
            ],
            "Could not install Kokoro ONNX packages",
            timeout=900,
        )

    def _download(self, url: str, destination: Path, repair: bool) -> None:
        if destination.is_file() and destination.stat().st_size > 0 and not repair:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(delete=False, dir=destination.parent) as temporary:
                temporary_path = Path(temporary.name)
                with urllib.request.urlopen(url, timeout=120) as response:
                    shutil.copyfileobj(response, temporary)
        except OSError as error:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
            raise ValueError(
                f"Could not download {destination.name}. Check your network connection and retry setup."
            ) from error
        assert temporary_path is not None
        if temporary_path.stat().st_size == 0:
            temporary_path.unlink(missing_ok=True)
            raise ValueError(f"Downloaded an empty file for {destination.name}.")
        temporary_path.replace(destination)

    def _list_managed_voices(self) -> list[str]:
        output = self._run(
            [
                str(self.paths.python),
                str(self.paths.wrapper),
                "--model",
                str(self.paths.model),
                "--voices-data",
                str(self.paths.voices_data),
                "--list-voices",
            ],
            "Could not read Kokoro voices",
            timeout=180,
        )
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _validate_preview(self, payload: TtsSettingsUpdate, voice_id: str) -> None:
        adapter = ManagedKokoroOnnxAdapter(
            Path(payload.python_path) if payload.python_path else None,
            Path(payload.executable) if payload.executable else None,
            Path(payload.model_path) if payload.model_path else None,
            Path(payload.voices_data_path) if payload.voices_data_path else None,
            Path(payload.voice_registry_path) if payload.voice_registry_path else None,
        )
        adapter.preview(
            "Echodraft Kokoro setup is ready.",
            voice_id,
            self.paths.probe,
            DirectionProfile(scopeType="system", scopeId="kokoro-setup"),
        )
        self.paths.probe.unlink(missing_ok=True)

    def _run(self, command: list[str], failure_prefix: str, timeout: int) -> str:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"{failure_prefix}: {detail or 'the command failed without details.'}")
        return completed.stdout

    def _progress(self, job_id: str, phase: str, message: str) -> None:
        step = next((index for index, item in enumerate(PHASES, 1) if item[0] == phase), 1)
        self.jobs_repository.set_progress(
            job_id,
            {
                "phase": phase,
                "message": message,
                "step": step,
                "total": len(PHASES),
            },
        )

    def _write_state(self, state: str, message: str) -> None:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.state.write_text(
            json.dumps({"state": state, "message": message}, indent=2),
            encoding="utf-8",
        )

    def _read_state(self) -> dict[str, object]:
        if not self.paths.state.is_file():
            return {}
        try:
            return cast(dict[str, object], json.loads(self.paths.state.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return {}

    def _steps(self, state: str, readiness_message: str | None) -> list[KokoroSetupStep]:
        done = {
            "checking_python": True,
            "creating_runtime": self.paths.root.exists(),
            "installing_packages": self.paths.python.is_file(),
            "downloading_model": self.paths.model.is_file(),
            "downloading_voice_data": self.paths.voices_data.is_file(),
            "building_voice_registry": self.paths.voice_registry.is_file(),
            "validating_preview": state in {"ready", "active"},
            "saving_settings": state == "active",
            "completed": state == "active",
        }
        steps: list[KokoroSetupStep] = []
        failed_message = readiness_message if state in {"failed", "incomplete"} else None
        for phase, label in PHASES:
            status = "done" if done.get(phase) else "pending"
            message = None
            if failed_message and status == "pending":
                status = "failed" if state == "failed" else "pending"
                message = failed_message
                failed_message = None
            steps.append(KokoroSetupStep(phase=phase, label=label, status=status, message=message))
        return steps

    def _write_wrapper(self) -> None:
        write_managed_wrapper(self.paths.wrapper)


def write_managed_wrapper(wrapper_path: Path) -> None:
    """Idempotently (re)write the managed Kokoro helper to the current ``WRAPPER_SOURCE``.

    The wrapper is generated content, so any on-disk copy that differs from the
    current source (e.g. an older install that hardcoded ``speed=1.0``) is
    refreshed. Callers use this both at setup time and lazily before each render
    so existing installs pick up wrapper fixes without a manual repair.

    The refresh is atomic (temp file + ``os.replace`` in the same directory) so a
    concurrent render never observes a mid-truncate wrapper.
    """
    if wrapper_path.is_file() and wrapper_path.read_text(encoding="utf-8") == WRAPPER_SOURCE:
        return
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=wrapper_path.parent, delete=False
    ) as temporary:
        temporary.write(WRAPPER_SOURCE)
        temporary_path = Path(temporary.name)
    if os.name != "nt":
        temporary_path.chmod(0o755)
    os.replace(temporary_path, wrapper_path)


WRAPPER_SOURCE = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro


def read_registry(path: str | None) -> set[str]:
    if not path:
        return set()
    registry = Path(path)
    if not registry.is_file():
        return set()
    return {
        line.strip()
        for line in registry.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Echodraft managed Kokoro ONNX helper")
    parser.add_argument("--model", required=True)
    parser.add_argument("--voices-data", required=True)
    parser.add_argument("--voice-registry")
    parser.add_argument("--voice")
    parser.add_argument("--text")
    parser.add_argument("--output")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--list-voices", action="store_true")
    args = parser.parse_args()

    kokoro = Kokoro(args.model, args.voices_data)
    voices = sorted(kokoro.get_voices())
    if args.list_voices:
        print("\n".join(voices))
        return 0

    if not args.voice or not args.text or not args.output:
        parser.error("--voice, --text, and --output are required unless --list-voices is used")

    allowed = read_registry(args.voice_registry) or set(voices)
    if args.voice not in allowed:
        print(f"Kokoro voice '{args.voice}' is not registered locally.", file=sys.stderr)
        return 2

    samples, sample_rate = kokoro.create(args.text, voice=args.voice, speed=args.speed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), samples, sample_rate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
