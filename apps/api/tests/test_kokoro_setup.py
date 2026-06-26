import stat
import time
from pathlib import Path

import pytest

from echodraft_api.kokoro_setup import ManagedKokoroSetupService, managed_python_path


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
    executable = tmp_path / "echodraft-kokoro"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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
