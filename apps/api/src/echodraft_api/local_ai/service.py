from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]

from echodraft_domain import (
    LocalAiHealth,
    LocalAiInstallation,
    LocalAiInstallJob,
    LocalAiInstallRequest,
    LocalAiModelCatalogItem,
)

from ..container import AppContainer
from ..kokoro_setup import ManagedKokoroSetupService


@dataclass(frozen=True)
class CatalogEntry:
    model_key: str
    display_name: str
    capability: str
    provider: str
    install_type: str
    required: bool
    command: str | None
    version_args: tuple[str, ...]
    packages: dict[str, str]
    ollama_model: str | None
    size_mb: int | None
    license_summary: str | None
    license_note: str | None
    description: str | None


class LocalAiService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.catalog_path = Path(__file__).with_name("model_catalog.yaml")
        self.root = container.settings.local_ai_root
        self.logs_root = self.root / "logs"

    def catalog(self) -> list[LocalAiModelCatalogItem]:
        installations = {item.model_key: item for item in self.container.local_ai.installations()}
        result: list[LocalAiModelCatalogItem] = []
        for entry in self._entries():
            installation = installations.get(entry.model_key)
            health = self.health(entry.model_key)
            result.append(
                LocalAiModelCatalogItem(
                    modelKey=entry.model_key,
                    displayName=entry.display_name,
                    capability=entry.capability,
                    provider=entry.provider,
                    installType=entry.install_type,
                    required=entry.required,
                    sizeMb=entry.size_mb,
                    licenseSummary=entry.license_summary,
                    licenseNote=entry.license_note,
                    description=entry.description,
                    status=installation.status if installation else "not_installed",
                    health=health.status,
                    installPath=installation.install_path if installation else health.install_path,
                    lastVerifiedAt=installation.last_verified_at if installation else None,
                )
            )
        return result

    def installations(self) -> list[LocalAiInstallation]:
        return self.container.local_ai.installations()

    def install_job(self, job_id: str) -> LocalAiInstallJob | None:
        return self.container.local_ai.install_job(job_id)

    def health(self, model_key: str) -> LocalAiHealth:
        entry = self._entry(model_key)
        if entry.install_type == "system_tool":
            return self._system_tool_health(entry)
        if entry.install_type == "ollama_model":
            return self._ollama_model_health(entry)
        if entry.install_type == "kokoro_managed":
            return self._kokoro_health(entry)
        return LocalAiHealth(
            modelKey=entry.model_key,
            status="unsupported",
            ready=False,
            message=f"Install type {entry.install_type} is not supported yet.",
            checkedAt=datetime.now(UTC),
        )

    def validate_install_request(self, model_key: str, request: LocalAiInstallRequest) -> None:
        self._validate_install_request(self._entry(model_key), request)

    def verify(self, model_key: str) -> LocalAiInstallation:
        entry = self._entry(model_key)
        health = self.health(model_key)
        return self.container.local_ai.upsert_installation(
            model_key=entry.model_key,
            display_name=entry.display_name,
            capability=entry.capability,
            provider=entry.provider,
            status="installed" if health.ready else "failed",
            version=health.version,
            install_path=health.install_path,
            size_bytes=self._size_bytes(entry, health),
            license_summary=entry.license_summary,
            error_message=None if health.ready else health.message,
        )

    def install(self, job_id: str, model_key: str, request: LocalAiInstallRequest) -> None:
        entry = self._entry(model_key)
        logs_path = self._prepare_install_job(job_id, entry)
        try:
            self._validate_install_request(entry, request)
            self._progress(job_id, "running", 5, "Preparing local installation.")
            if entry.install_type == "system_tool":
                self._install_system_tool(job_id, entry, logs_path)
            elif entry.install_type == "ollama_model":
                self._install_ollama_model(entry, logs_path)
            elif entry.install_type == "kokoro_managed":
                self._install_kokoro(job_id, entry)
            else:
                raise ValueError(f"Install type {entry.install_type} is not supported yet.")
            self.verify(entry.model_key)
            self._progress(job_id, "succeeded", 100, "Installation verified.")
        except Exception as error:
            self.container.local_ai.upsert_installation(
                model_key=entry.model_key,
                display_name=entry.display_name,
                capability=entry.capability,
                provider=entry.provider,
                status="failed",
                license_summary=entry.license_summary,
                error_message=str(error),
            )
            self._progress(job_id, "failed", 100, "Installation failed.", str(error))
            raise

    def uninstall(self, model_key: str) -> None:
        entry = self._entry(model_key)
        if entry.install_type == "system_tool":
            raise ValueError("Model Center does not uninstall system packages.")
        if entry.install_type == "ollama_model":
            command = entry.ollama_model
            executable = shutil.which("ollama")
            if command and executable:
                subprocess.run([executable, "rm", command], capture_output=True, text=True, check=False)
        elif entry.install_type == "kokoro_managed":
            shutil.rmtree(self.container.settings.kokoro_runtime_root, ignore_errors=True)
        self.container.local_ai.remove_installation(model_key)

    def _entries(self) -> list[CatalogEntry]:
        raw = yaml.safe_load(self.catalog_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("models"), dict):
            raise ValueError("Local AI model catalog is malformed.")
        models = cast(dict[str, object], raw["models"])
        return [self._entry_from_raw(key, value) for key, value in models.items()]

    def _entry(self, model_key: str) -> CatalogEntry:
        for entry in self._entries():
            if entry.model_key == model_key:
                return entry
        raise KeyError(model_key)

    def _entry_from_raw(self, model_key: str, value: object) -> CatalogEntry:
        if not isinstance(value, dict):
            raise ValueError(f"Model catalog entry {model_key} is malformed.")
        data = cast(dict[str, object], value)
        packages = data.get("packages")
        version_args = data.get("version_args")
        size_mb = data.get("size_mb")
        return CatalogEntry(
            model_key=model_key,
            display_name=self._required_str(data, "display_name"),
            capability=self._required_str(data, "capability"),
            provider=self._required_str(data, "provider"),
            install_type=self._required_str(data, "install_type"),
            required=bool(data.get("required", False)),
            command=self._optional_str(data.get("command")),
            version_args=tuple(str(item) for item in version_args)
            if isinstance(version_args, list)
            else (),
            packages={str(key): str(item) for key, item in packages.items()}
            if isinstance(packages, dict)
            else {},
            ollama_model=self._optional_str(data.get("ollama_model")),
            size_mb=size_mb if isinstance(size_mb, int) else None,
            license_summary=self._optional_str(data.get("license_summary")),
            license_note=self._optional_str(data.get("license_note")),
            description=self._optional_str(data.get("description")),
        )

    def _system_tool_health(self, entry: CatalogEntry) -> LocalAiHealth:
        if not entry.command:
            return self._health(entry, "missing", False, "No command is configured for this tool.")
        executable = shutil.which(entry.command)
        if not executable:
            return self._health(entry, "missing", False, f"{entry.display_name} is not on PATH.")
        version = self._version([executable, *entry.version_args])
        return self._health(
            entry,
            "ready",
            True,
            f"{entry.display_name} is available.",
            version=version,
            install_path=executable,
        )

    def _ollama_model_health(self, entry: CatalogEntry) -> LocalAiHealth:
        if not entry.ollama_model:
            return self._health(entry, "missing", False, "No Ollama model name is configured.")
        if not shutil.which("ollama"):
            return self._health(entry, "missing", False, "Ollama is not installed or not on PATH.")
        try:
            models = self._ollama_tags()
        except ValueError as error:
            return self._health(entry, "unavailable", False, str(error))
        match = next((item for item in models if item.get("name") == entry.ollama_model), None)
        if not match:
            return self._health(
                entry,
                "missing",
                False,
                f"Ollama model {entry.ollama_model} has not been pulled locally.",
            )
        return self._health(
            entry,
            "ready",
            True,
            f"Ollama model {entry.ollama_model} is available.",
            version=str(match.get("digest") or match.get("modified_at") or ""),
            install_path=f"ollama://{entry.ollama_model}",
            details={"size": match.get("size", 0)},
        )

    def _kokoro_health(self, entry: CatalogEntry) -> LocalAiHealth:
        status = ManagedKokoroSetupService(
            self.container.settings, self.container.tts_settings, self.container.jobs_repository
        ).status()
        return self._health(
            entry,
            "ready" if status.ready else status.state,
            status.ready,
            status.message or status.next_action,
            version=None,
            install_path=status.runtime_root,
            details={"voices": status.available_voices, "setupMode": status.setup_mode},
        )

    def _install_system_tool(self, job_id: str, entry: CatalogEntry, logs_path: Path) -> None:
        existing = self._system_tool_health(entry)
        if existing.ready:
            self._progress(job_id, "running", 80, "System tool is already installed.")
            return
        command = self._system_install_command(entry)
        self._run_logged(command, logs_path, timeout=1800)

    def _install_ollama_model(self, entry: CatalogEntry, logs_path: Path) -> None:
        if not entry.ollama_model:
            raise ValueError("No Ollama model is configured for this catalog entry.")
        executable = shutil.which("ollama")
        if not executable:
            raise ValueError("Install the Ollama runtime before pulling Ollama models.")
        self._run_logged([executable, "pull", entry.ollama_model], logs_path, timeout=7200)

    def _install_kokoro(self, job_id: str, entry: CatalogEntry) -> None:
        self._progress(job_id, "running", 20, "Installing managed Kokoro runtime.")
        ManagedKokoroSetupService(
            self.container.settings, self.container.tts_settings, self.container.jobs_repository
        ).install(job_id, repair=True)
        self._progress(job_id, "running", 95, "Kokoro runtime installed.")

    def _system_install_command(self, entry: CatalogEntry) -> list[str]:
        system = platform.system()
        if system == "Darwin":
            package = entry.packages.get("homebrew")
            if not package:
                raise ValueError(f"No Homebrew package is configured for {entry.display_name}.")
            brew = shutil.which("brew")
            if not brew:
                raise ValueError("Homebrew is required for automatic macOS system-tool installs.")
            return [brew, "install", package]
        if system == "Windows":
            package = entry.packages.get("winget")
            winget = shutil.which("winget")
            if not package or not winget:
                raise ValueError("winget is required for automatic Windows system-tool installs.")
            return [
                winget,
                "install",
                "--id",
                package,
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        if system == "Linux":
            package = entry.packages.get("apt")
            apt = shutil.which("apt-get")
            if not package or not apt:
                raise ValueError("apt-get is required for automatic Linux system-tool installs.")
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                return [apt, "install", "-y", package]
            sudo = shutil.which("sudo")
            if not sudo:
                raise ValueError("sudo is required to install system packages with apt-get.")
            return [sudo, "-n", apt, "install", "-y", package]
        raise ValueError(f"Automatic system-tool installation is not supported on {system}.")

    def _prepare_install_job(self, job_id: str, entry: CatalogEntry) -> Path:
        self.logs_root.mkdir(parents=True, exist_ok=True)
        logs_path = self.logs_root / f"{job_id}.{entry.model_key}.log"
        if not self.container.local_ai.install_job(job_id):
            self.container.local_ai.create_install_job(job_id, entry.model_key, str(logs_path))
        return logs_path

    def _validate_install_request(
        self, entry: CatalogEntry, request: LocalAiInstallRequest
    ) -> None:
        if entry.install_type == "system_tool" and not request.confirm_system_install:
            raise ValueError("Confirm system package installation before installing this tool.")
        if entry.install_type in {"system_tool", "ollama_model", "kokoro_managed"}:
            if not request.confirm_network_download:
                raise ValueError("Confirm local network download before installing this model or tool.")
        if entry.license_summary and not request.confirm_third_party_license:
            raise ValueError("Confirm third-party license review before installing this model or tool.")

    def _progress(
        self,
        job_id: str,
        status: str,
        progress_percent: int,
        current_step: str,
        error_message: str | None = None,
    ) -> None:
        self.container.jobs_repository.set_progress(
            job_id,
            {
                "phase": "local_ai_install",
                "message": current_step,
                "progressPercent": progress_percent,
            },
        )
        try:
            self.container.local_ai.update_install_job(
                job_id,
                status=status,
                progress_percent=progress_percent,
                current_step=current_step,
                error_message=error_message,
            )
        except KeyError:
            pass

    def _run_logged(self, command: list[str], logs_path: Path, timeout: int) -> str:
        logs_path.parent.mkdir(parents=True, exist_ok=True)
        with logs_path.open("a", encoding="utf-8") as log:
            log.write(f"$ {' '.join(command)}\n")
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
            log.write(completed.stdout)
            log.write(completed.stderr)
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(f"Install command failed: {detail or 'no details were returned.'}")
        return completed.stdout

    def _ollama_tags(self) -> list[dict[str, object]]:
        url = f"{self.container.settings.ollama_base_url}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ValueError(f"Ollama is not reachable at {self.container.settings.ollama_base_url}.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("Ollama returned an unexpected model list response.")
        models: list[dict[str, object]] = []
        for item in payload["models"]:
            if isinstance(item, dict):
                models.append(cast(dict[str, object], item))
        return models

    def _version(self, command: list[str]) -> str | None:
        if len(command) == 1:
            return None
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        except OSError:
            return None
        output = completed.stdout.strip() or completed.stderr.strip()
        return output.splitlines()[0] if output else None

    def _size_bytes(self, entry: CatalogEntry, health: LocalAiHealth) -> int | None:
        size = health.details.get("size")
        if isinstance(size, int):
            return size
        return entry.size_mb * 1024 * 1024 if entry.size_mb else None

    def _health(
        self,
        entry: CatalogEntry,
        status: str,
        ready: bool,
        message: str,
        *,
        version: str | None = None,
        install_path: str | None = None,
        details: dict[str, object] | None = None,
    ) -> LocalAiHealth:
        return LocalAiHealth(
            modelKey=entry.model_key,
            status=status,
            ready=ready,
            message=message,
            version=version,
            installPath=install_path,
            checkedAt=datetime.now(UTC),
            details=details or {},
        )

    @staticmethod
    def _required_str(data: dict[str, object], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Model catalog entry is missing {key}.")
        return value

    @staticmethod
    def _optional_str(value: object) -> str | None:
        return value if isinstance(value, str) and value.strip() else None
