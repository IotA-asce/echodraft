import time
from pathlib import Path

import pytest

import echodraft_api.local_llm as local_llm
from echodraft_api.local_llm import OllamaGenerateResult, parse_llm_json_object, validate_json_schema


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


class FakeProvider:
    calls = 0

    def __init__(self, _base_url: str) -> None:
        pass

    def tags(self) -> list[dict[str, object]]:
        return [{"name": "qwen3:4b"}, {"name": "qwen3-embedding"}]

    def generate_json(
        self, _model: str, _prompt: str, _schema: dict[str, object]
    ) -> OllamaGenerateResult:
        self.__class__.calls += 1
        if self.__class__.calls == 1:
            return OllamaGenerateResult(response={"characters": []}, raw={"response": "{}"})
        response: dict[str, object] = {
            "characters": [{"name": "Mara", "evidence": "Mara said hello", "confidence": 0.92}],
            "warnings": [],
        }
        return OllamaGenerateResult(response=response, raw={"response": "{}"})

    def embed(self, _request: object) -> object:
        from echodraft_domain import EmbeddingResult

        return EmbeddingResult(model="qwen3-embedding", embeddings=[[0.1, 0.2]])


class LatestTaggedEmbeddingProvider(FakeProvider):
    def tags(self) -> list[dict[str, object]]:
        return [{"name": "qwen3-embedding:latest", "model": "qwen3-embedding:latest"}]


class WrappedJsonProvider(FakeProvider):
    def generate_json(
        self, _model: str, _prompt: str, _schema: dict[str, object]
    ) -> OllamaGenerateResult:
        raw_response = """
<think>
I should identify the observed character and then return the schema.
</think>
```json
{
  "characters": [
    {"name": "Mara", "evidence": "Mara said hello", "confidence": 0.92}
  ],
  "warnings": []
}
```
"""
        return OllamaGenerateResult(
            response=parse_llm_json_object(raw_response),
            raw={"response": raw_response},
        )


def test_schema_validation_requires_declared_fields() -> None:
    errors = validate_json_schema({"characters": []}, local_llm.DEFAULT_EXTRACTION_SCHEMA)
    assert "$.warnings is required" in errors


def test_parse_llm_json_object_accepts_wrapped_qwen_output() -> None:
    response = """
<think>{"draft": "not the answer"}</think>
Here is the JSON:
```json
{"characters": [{"name": "Mara", "confidence": 0.9}], "warnings": []}
```
Done.
"""

    parsed = parse_llm_json_object(response)

    assert parsed["characters"] == [{"name": "Mara", "confidence": 0.9}]
    assert parsed["warnings"] == []


def test_llm_extraction_job_records_retry_and_result(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeProvider.calls = 0
    monkeypatch.setattr(local_llm, "OllamaProvider", FakeProvider)
    project = project_with_source(client)

    response = client.post(
        f"/api/v1/projects/{project}/local-llm/extractions",
        json={"model": "qwen3:4b"},
    )
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded", job["errorMessage"]

    runs = client.get(f"/api/v1/projects/{project}/llm-runs").json()
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["retries"] == 1
    assert runs[0]["result"]["characters"][0]["name"] == "Mara"
    assert Path(runs[0]["promptPath"]).is_file()
    assert Path(runs[0]["responsePath"]).is_file()


def test_llm_extraction_accepts_wrapped_json_response(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_llm, "OllamaProvider", WrappedJsonProvider)
    project = project_with_source(client)

    response = client.post(
        f"/api/v1/projects/{project}/local-llm/extractions",
        json={"model": "qwen3:4b"},
    )
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "succeeded", job["errorMessage"]

    runs = client.get(f"/api/v1/projects/{project}/llm-runs").json()
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["result"]["characters"][0]["name"] == "Mara"


def test_embedding_endpoint_uses_installed_ollama_model(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_llm, "OllamaProvider", FakeProvider)
    response = client.post(
        "/api/v1/local-llm/embeddings",
        json={"model": "qwen3-embedding", "input": "Mara"},
    )
    assert response.status_code == 200
    assert response.json()["embeddings"] == [[0.1, 0.2]]


def test_embedding_endpoint_accepts_ollama_latest_tag(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_llm, "OllamaProvider", LatestTaggedEmbeddingProvider)

    response = client.post(
        "/api/v1/local-llm/embeddings",
        json={"model": "qwen3-embedding", "input": "Mara"},
    )

    assert response.status_code == 200
    assert response.json()["embeddings"] == [[0.1, 0.2]]


def test_llm_extraction_fails_closed_when_model_missing(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MissingProvider(FakeProvider):
        def tags(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(local_llm, "OllamaProvider", MissingProvider)
    project = project_with_source(client)
    response = client.post(
        f"/api/v1/projects/{project}/local-llm/extractions",
        json={"model": "qwen3:4b"},
    )
    assert response.status_code == 202
    job = wait_for_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "not installed" in job["errorMessage"]
