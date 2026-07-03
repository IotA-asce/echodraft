import os
import stat
import time
import wave
from pathlib import Path

import pytest

from echodraft_api.kokoro_setup import (
    WRAPPER_SOURCE,
    ManagedKokoroPaths,
    ManagedKokoroSetupService,
    managed_python_path,
)


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def install_payload(repair: bool = False) -> dict:
    return {
        "confirmNetworkDownload": True,
        "confirmThirdPartyLicense": True,
        "repair": repair,
    }


def patch_successful_install(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_create_virtualenv(self: ManagedKokoroSetupService) -> None:
        self.paths.python.parent.mkdir(parents=True, exist_ok=True)
        self.paths.python.write_text("# python", encoding="utf-8")

    def fake_download(
        self: ManagedKokoroSetupService, _url: str, destination: Path, repair: bool
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if repair or not destination.exists():
            destination.write_bytes(b"managed-kokoro-test-asset")

    monkeypatch.setattr(ManagedKokoroSetupService, "_create_virtualenv", fake_create_virtualenv)
    monkeypatch.setattr(ManagedKokoroSetupService, "_install_packages", lambda self: None)
    monkeypatch.setattr(ManagedKokoroSetupService, "_download", fake_download)
    monkeypatch.setattr(
        ManagedKokoroSetupService, "_list_managed_voices", lambda self: ["af_heart", "af_sarah"]
    )
    monkeypatch.setattr(ManagedKokoroSetupService, "_validate_preview", lambda self, payload, voice: None)


def test_kokoro_setup_status_reports_not_started(client) -> None:
    response = client.get("/api/v1/settings/tts/kokoro/setup")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "not_started"
    assert body["ready"] is False
    assert body["setupMode"] == "managed_onnx"
    assert "Set up Kokoro" in body["nextAction"]


def test_managed_kokoro_install_job_saves_settings_and_lists_voices(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_successful_install(monkeypatch)

    response = client.post("/api/v1/settings/tts/kokoro/setup/install", json=install_payload())
    assert response.status_code == 200
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded"
    assert job["progress"]["phase"] == "completed"

    settings = client.get("/api/v1/settings/tts").json()
    assert settings["provider"] == "kokoro"
    assert settings["setupMode"] == "managed_onnx"
    assert settings["ready"] is True
    assert settings["availableVoices"] == ["af_heart", "af_sarah"]

    setup = client.get("/api/v1/settings/tts/kokoro/setup").json()
    assert setup["state"] == "active"
    assert not setup["executable"].endswith(".py")
    assert setup["availableVoices"] == ["af_heart", "af_sarah"]


def test_managed_kokoro_install_requires_explicit_confirmations(client) -> None:
    response = client.post(
        "/api/v1/settings/tts/kokoro/setup/install",
        json={"confirmNetworkDownload": False, "confirmThirdPartyLicense": True},
    )
    assert response.status_code == 422
    assert "Confirm" in response.json()["detail"]


def test_failed_managed_install_preserves_existing_working_settings(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_successful_install(monkeypatch)

    client.put("/api/v1/settings/tts", json={"provider": "mock"})

    def fail_preview(self: ManagedKokoroSetupService, _payload, _voice: str) -> None:
        raise ValueError("Kokoro preview failed. Check the local runtime and retry setup.")

    monkeypatch.setattr(ManagedKokoroSetupService, "_validate_preview", fail_preview)

    response = client.post("/api/v1/settings/tts/kokoro/setup/install", json=install_payload(repair=True))
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "Kokoro preview failed" in job["errorMessage"]

    settings = client.get("/api/v1/settings/tts").json()
    assert settings["provider"] == "mock"
    assert settings["ready"] is True

    setup = client.get("/api/v1/settings/tts/kokoro/setup").json()
    assert setup["state"] == "failed"
    assert "Repair setup" in setup["nextAction"]


def test_install_failures_are_actionable(client, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_packages(self: ManagedKokoroSetupService) -> None:
        raise ValueError("Could not install Kokoro ONNX packages: pip is unavailable.")

    patch_successful_install(monkeypatch)
    monkeypatch.setattr(ManagedKokoroSetupService, "_install_packages", fail_packages)

    response = client.post("/api/v1/settings/tts/kokoro/setup/install", json=install_payload())
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "pip is unavailable" in job["errorMessage"]


def test_empty_managed_voice_list_fails_before_saving(client, monkeypatch: pytest.MonkeyPatch) -> None:
    patch_successful_install(monkeypatch)
    monkeypatch.setattr(ManagedKokoroSetupService, "_list_managed_voices", lambda self: [])

    response = client.post("/api/v1/settings/tts/kokoro/setup/install", json=install_payload())
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "no voices" in job["errorMessage"]
    assert client.get("/api/v1/settings/tts").json()["provider"] == "mock"


def test_existing_custom_kokoro_adapter_settings_still_validate(client, tmp_path: Path) -> None:
    executable = tmp_path / ("echodraft-kokoro.cmd" if os.name == "nt" else "echodraft-kokoro")
    executable.write_text(
        "@echo off\r\nexit /b 0\r\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    model = tmp_path / "kokoro.onnx"
    model.write_bytes(b"model")
    registry = tmp_path / "voices.txt"
    registry.write_text("af_heart\n", encoding="utf-8")

    response = client.put(
        "/api/v1/settings/tts",
        json={
            "provider": "kokoro",
            "setupMode": "custom_adapter",
            "executable": str(executable),
            "modelPath": str(model),
            "voiceRegistryPath": str(registry),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["setupMode"] == "custom_adapter"
    assert body["ready"] is True
    assert body["availableVoices"] == ["af_heart"]


def test_managed_python_path_is_platform_specific(tmp_path: Path) -> None:
    assert managed_python_path(tmp_path, "Windows") == tmp_path / "venv" / "Scripts" / "python.exe"
    assert managed_python_path(tmp_path, "Darwin") == tmp_path / "venv" / "bin" / "python"
    assert managed_python_path(tmp_path, "Linux") == tmp_path / "venv" / "bin" / "python"


def test_managed_wrapper_avoids_python_suffix_and_rewrites_only_when_changed(tmp_path: Path) -> None:
    paths = ManagedKokoroPaths(tmp_path / "managed-onnx-v1")
    assert paths.wrapper.name == "echodraft_kokoro_onnx"
    assert paths.wrapper.suffix == ""

    service = object.__new__(ManagedKokoroSetupService)
    service.paths = paths
    paths.root.mkdir(parents=True)

    service._write_wrapper()
    first_mtime = paths.wrapper.stat().st_mtime_ns
    service._write_wrapper()
    assert paths.wrapper.stat().st_mtime_ns == first_mtime

    paths.wrapper.write_text("outdated helper", encoding="utf-8")
    service._write_wrapper()
    assert paths.wrapper.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


def test_managed_wrapper_source_transmits_speed() -> None:
    assert "--speed" in WRAPPER_SOURCE
    assert "speed=args.speed" in WRAPPER_SOURCE
    assert "speed=1.0)" not in WRAPPER_SOURCE


def test_managed_wrapper_source_writes_pcm16() -> None:
    # The managed wrapper must write signed 16-bit PCM; a float WAV (soundfile's default)
    # is unreadable by the stdlib ``wave`` decoder used across rendering/assembly.
    assert 'subtype="PCM_16"' in WRAPPER_SOURCE


def _ready_managed_adapter(tmp_path: Path, stale_wrapper: bool):
    from echodraft_api.tts_providers import ManagedKokoroOnnxAdapter

    python = tmp_path / "python"
    python.write_text("# python", encoding="utf-8")
    wrapper = tmp_path / "echodraft_kokoro_onnx"
    wrapper.write_text("stale helper" if stale_wrapper else WRAPPER_SOURCE, encoding="utf-8")
    model = tmp_path / "kokoro-v1.0.onnx"
    model.write_bytes(b"model")
    voices_data = tmp_path / "voices-v1.0.bin"
    voices_data.write_bytes(b"voices")
    registry = tmp_path / "voices.txt"
    registry.write_text("af_heart\n", encoding="utf-8")
    adapter = ManagedKokoroOnnxAdapter(python, wrapper, model, voices_data, registry)
    return adapter, wrapper


def test_managed_kokoro_preview_transmits_speed_and_self_heals_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from echodraft_domain import DirectionProfile

    adapter, wrapper = _ready_managed_adapter(tmp_path, stale_wrapper=True)
    captured: dict[str, list[str]] = {}

    def fake_run(command, provider_name, *, timeout, stdin=None):  # type: ignore[no-untyped-def]
        captured["command"] = command
        output = Path(command[command.index("--output") + 1])
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16000)
            target.writeframes(b"\x00\x00" * 1000)

    monkeypatch.setattr("echodraft_api.tts_providers._run_tts_command", fake_run)

    adapter.preview(
        "Hello there.",
        "af_heart",
        tmp_path / "out.wav",
        DirectionProfile(scopeType="segment", scopeId="seg", pace=1.25),
    )

    command = captured["command"]
    assert "--speed" in command
    assert command[command.index("--speed") + 1] == "1.250"
    # The stale on-disk wrapper is refreshed to the current source before running.
    assert wrapper.read_text(encoding="utf-8") == WRAPPER_SOURCE
