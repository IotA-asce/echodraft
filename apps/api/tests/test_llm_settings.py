import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from echodraft_api.llm_providers import OpenAiCompatProvider
from echodraft_api.local_llm import _inference_cache_key
from echodraft_db import Database, LlmSettingsRepository, LlmSettingsRow


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


def test_llm_settings_get_recovers_from_concurrent_first_insert(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic regression test for the reachable first-insert race.

    Several pipeline stages construct ``LocalLlmService`` from inside a
    ``ThreadPoolExecutor`` fan-out, and each construction calls
    ``LlmSettingsRepository.get()``. On a fresh DB, two threads can both
    observe ``record is None`` and race to INSERT id=1; the loser's
    ``commit()`` must recover by re-reading the winner's row instead of
    letting ``IntegrityError`` escape.

    Orchestrating that interleaving via real threads is timing-dependent, so
    instead we simulate the race directly: patch ``Session.commit`` so that,
    on the first call made from inside ``get()``, a *separate* session wins
    the race by inserting and committing the singleton row first. The
    patched call then proceeds to the real ``commit()``, which hits SQLite's
    genuine primary-key constraint and raises a real ``IntegrityError`` --
    exercising the exact except-branch under test.
    """
    from sqlalchemy.orm import Session

    from echodraft_db.models import LlmSettingsRecord

    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    real_commit = Session.commit
    calls = {"n": 0}

    def racing_commit(self: Session) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            # Simulate a second thread's get() winning the race.
            with database.session() as other_session:
                other_session.add(LlmSettingsRecord(id=1))
                real_commit(other_session)
        real_commit(self)

    monkeypatch.setattr(Session, "commit", racing_commit)

    row = repo.get()

    assert calls["n"] == 1  # get() calls session.commit() exactly once
    assert row.provider == "ollama"
    assert row.cloud_consent is False


def test_llm_settings_get_is_race_tolerant_under_concurrent_first_access(tmp_path) -> None:
    """Concurrency smoke test alongside the deterministic test above: several
    real threads hammering ``get()`` on a fresh DB at once must never raise
    and must always agree on the singleton row. GIL/timing mean this does
    not reliably land inside the INSERT-vs-INSERT window by itself, so it is
    a smoke check (no crash, no disagreement), not the primary regression
    coverage for the race.
    """
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def call_get() -> LlmSettingsRow:
        barrier.wait()  # line every thread up so they all hit `get()` at once
        return repo.get()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        rows = list(executor.map(lambda _: call_get(), range(worker_count)))

    assert len(rows) == worker_count
    assert all(row.provider == "ollama" for row in rows)
    assert all(row.cloud_consent is False for row in rows)


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


def test_settings_endpoint_round_trip_never_echoes_key(client) -> None:
    initial = client.get("/api/v1/llm/settings").json()
    assert initial["provider"] == "ollama"
    assert initial["hasApiKey"] is False

    response = client.put(
        "/api/v1/llm/settings",
        json={
            "provider": "openai_compat",
            "baseUrl": "https://api.x.ai/v1",
            "model": "grok-4.5",
            "apiKey": "xai-secret",
            "cloudConsent": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai_compat"
    assert body["hasApiKey"] is True
    assert "xai-secret" not in response.text

    # omitted apiKey keeps the stored key
    kept = client.put(
        "/api/v1/llm/settings",
        json={
            "provider": "openai_compat",
            "baseUrl": "https://api.x.ai/v1",
            "model": "grok-4.5",
            "cloudConsent": True,
        },
    ).json()
    assert kept["hasApiKey"] is True

    # explicit empty string clears it -> activation must now fail
    cleared = client.put(
        "/api/v1/llm/settings",
        json={
            "provider": "openai_compat",
            "baseUrl": "https://api.x.ai/v1",
            "model": "grok-4.5",
            "apiKey": "",
            "cloudConsent": True,
        },
    )
    assert cleared.status_code == 422


def test_settings_endpoint_rejects_consentless_cloud(client) -> None:
    response = client.put(
        "/api/v1/llm/settings",
        json={
            "provider": "openai_compat",
            "baseUrl": "https://api.x.ai/v1",
            "model": "grok-4.5",
            "apiKey": "xai-secret",
            "cloudConsent": False,
        },
    )
    assert response.status_code == 422
    assert "consent" in response.json()["detail"].lower()


def test_connection_test_endpoint(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        OpenAiCompatProvider,
        "available_models",
        lambda self, **kw: ["grok-4.5", "grok-4"],
    )
    body = client.post(
        "/api/v1/llm/settings/test",
        json={"baseUrl": "https://api.x.ai/v1", "apiKey": "k", "model": "grok-4.5"},
    ).json()
    assert body == {"ok": True, "models": ["grok-4.5", "grok-4"], "modelFound": True, "error": None}

    def boom(self, **kw):
        raise ValueError("cloud request failed for /models: HTTP 401 unauthorized")

    monkeypatch.setattr(OpenAiCompatProvider, "available_models", boom)
    body = client.post(
        "/api/v1/llm/settings/test",
        json={"baseUrl": "https://api.x.ai/v1", "apiKey": "bad"},
    ).json()
    assert body["ok"] is False
    assert "401" in body["error"]
