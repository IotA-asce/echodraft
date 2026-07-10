import time

import pytest

from echodraft_api.llm_providers import OpenAiCompatProvider
from echodraft_api.local_llm import _inference_cache_key
from echodraft_db import Database, LlmSettingsRepository


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(60):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_source(client) -> str:
    project = client.post(
        "/api/v1/projects", json={"title": "LLM", "rightsStatus": "declared"}
    ).json()["id"]
    job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("book.txt", b"Chapter 1\n\nMara said hello.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"
    return project


def test_llm_settings_defaults_to_local_ollama(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    row = repo.get()

    assert row.provider == "ollama"
    assert row.base_url is None
    assert row.model is None
    assert row.api_key is None
    assert row.cloud_consent is False


def test_llm_settings_update_round_trips(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    repo.update(
        provider="openai_compat",
        base_url="https://api.x.ai/v1",
        model="grok-4.5",
        api_key="xai-secret",
        cloud_consent=True,
    )
    row = repo.get()

    assert row.provider == "openai_compat"
    assert row.base_url == "https://api.x.ai/v1"
    assert row.model == "grok-4.5"
    assert row.api_key == "xai-secret"
    assert row.cloud_consent is True
    assert row.updated_at is not None


CLOUD_ENV = {
    "ECHODRAFT_LLM_PROVIDER": "openai_compat",
    "ECHODRAFT_LLM_BASE_URL": "https://api.x.ai/v1",
    "ECHODRAFT_LLM_MODEL": "grok-4.5",
    "ECHODRAFT_LLM_API_KEY": "xai-key",
    "ECHODRAFT_LLM_CLOUD_CONSENT": "1",
}


def _set_cloud_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    for key, value in {**CLOUD_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_cloud_provider_overrides_stage_model_and_records_provenance(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_cloud_env(monkeypatch)
    seen: dict[str, object] = {}

    def fake_infer(self, model, prompt, schema, *, temperature=None, seed=None):
        seen["model"] = model
        from echodraft_api.llm_providers import GenerateResult

        return GenerateResult(
            response={"characters": [], "warnings": []}, raw={"choices": []}
        )

    monkeypatch.setattr(OpenAiCompatProvider, "infer", fake_infer)
    monkeypatch.setattr(
        OpenAiCompatProvider, "available_models", lambda self, **kw: ["grok-4.5"]
    )
    project = project_with_source(client)

    job = client.post(
        f"/api/v1/projects/{project}/local-llm/extractions",
        json={"model": "qwen3:4b", "task": "structure_candidates"},
    ).json()
    assert wait_for_job(client, job["id"])["status"] == "succeeded"

    runs = client.get(f"/api/v1/projects/{project}/llm-runs").json()
    assert seen["model"] == "grok-4.5"           # stage default was overridden
    assert runs[0]["provider"] == "openai_compat"
    assert runs[0]["model"] == "grok-4.5"


def test_cloud_without_consent_fails_closed(client, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_cloud_env(monkeypatch, ECHODRAFT_LLM_CLOUD_CONSENT=None)
    project = project_with_source(client)

    job = client.post(
        f"/api/v1/projects/{project}/local-llm/extractions",
        json={"model": "qwen3:4b", "task": "structure_candidates"},
    ).json()

    assert wait_for_job(client, job["id"])["status"] == "failed"


def test_cache_key_provider_field_preserves_local_identity() -> None:
    schema: dict[str, object] = {"type": "object"}
    local_default = _inference_cache_key("qwen3:4b", "t", "p", schema)
    local_explicit = _inference_cache_key("qwen3:4b", "t", "p", schema, provider="ollama")
    cloud = _inference_cache_key("qwen3:4b", "t", "p", schema, provider="openai_compat")
    assert local_default == local_explicit   # existing cache entries keep their identity
    assert cloud != local_default            # cloud draws can never collide with local ones
