from __future__ import annotations

from dataclasses import dataclass

import pytest

import echodraft_api.local_ai.service as local_ai_service
from echodraft_api.local_ai import LocalAiService
from echodraft_domain import LocalAiInstallRequest


@dataclass
class CompletedCommand:
    returncode: int = 0
    stdout: str = "ffmpeg version test\n"
    stderr: str = ""


def test_local_ai_catalog_exposes_required_capabilities(client) -> None:
    response = client.get("/api/v1/local-ai/catalog")
    assert response.status_code == 200
    catalog = response.json()
    keys = {item["modelKey"] for item in catalog}
    assert {"poppler", "tesseract", "ffmpeg", "ollama", "kokoro_82m_onnx"}.issubset(keys)
    required = [item for item in catalog if item["required"]]
    assert required
    assert all("health" in item and "installType" in item for item in catalog)


def test_local_ai_install_requires_explicit_confirmations(client) -> None:
    response = client.post("/api/v1/local-ai/models/ffmpeg/install", json={})
    assert response.status_code == 422
    assert "Confirm system package installation" in response.json()["detail"]


def test_local_ai_unknown_catalog_item_returns_not_found(client) -> None:
    response = client.get("/api/v1/local-ai/models/not-real/health")
    assert response.status_code == 404


def test_verify_persists_system_tool_installation(app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        local_ai_service.shutil,
        "which",
        lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None,
    )
    monkeypatch.setattr(
        local_ai_service.subprocess,
        "run",
        lambda *_args, **_kwargs: CompletedCommand(),
    )

    installation = LocalAiService(app.state.container).verify("ffmpeg")

    assert installation.model_key == "ffmpeg"
    assert installation.status == "installed"
    assert installation.install_path == "/usr/bin/ffmpeg"
    assert app.state.container.local_ai.installation("ffmpeg") is not None


def test_verify_accepts_ollama_latest_tag(app, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        local_ai_service.shutil,
        "which",
        lambda command: "/usr/local/bin/ollama" if command == "ollama" else None,
    )
    monkeypatch.setattr(
        LocalAiService,
        "_ollama_tags",
        lambda _self: [
            {
                "name": "qwen3-embedding:latest",
                "model": "qwen3-embedding:latest",
                "digest": "digest-test",
                "size": 1234,
            }
        ],
    )

    installation = LocalAiService(app.state.container).verify("qwen3_embedding_ollama")

    assert installation.model_key == "qwen3_embedding_ollama"
    assert installation.status == "installed"
    assert installation.install_path == "ollama://qwen3-embedding:latest"
    assert installation.version == "digest-test"
    assert installation.size_bytes == 1234


def test_system_tool_install_uses_existing_tool_without_package_command(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> CompletedCommand:
        calls.append(command)
        return CompletedCommand(stdout="ffmpeg version test\n")

    monkeypatch.setattr(
        local_ai_service.shutil,
        "which",
        lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None,
    )
    monkeypatch.setattr(local_ai_service.subprocess, "run", fake_run)
    job = app.state.container.jobs_repository.create("local_ai.install", target_id="ffmpeg")

    LocalAiService(app.state.container).install(
        job.id,
        "ffmpeg",
        LocalAiInstallRequest(
            confirmNetworkDownload=True,
            confirmThirdPartyLicense=True,
            confirmSystemInstall=True,
        ),
    )

    installation = app.state.container.local_ai.installation("ffmpeg")
    assert installation and installation.status == "installed"
    assert calls == [["/usr/bin/ffmpeg", "-version"], ["/usr/bin/ffmpeg", "-version"]]
