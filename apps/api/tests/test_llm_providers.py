import io
import json
import urllib.error

import pytest

from echodraft_api import llm_providers
from echodraft_api.llm_providers import (
    EffectiveLlmSettings,
    OpenAiCompatProvider,
    ensure_cloud_ready,
    resolve_effective_llm_settings,
)
from echodraft_db import Database, LlmSettingsRepository

SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}


class FakeHttp:
    """Captures urlopen requests and replays canned responses."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, dict[str, object] | None, dict[str, str]]] = []

    def __call__(self, request, timeout=0):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append((request.full_url, body, dict(request.headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return False

            def read(self_inner) -> bytes:
                return json.dumps(response).encode("utf-8")

        return _Resp()


def chat_response(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"content": content}}]}


def http_error(status: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.x.ai/v1/x", status, "err", {}, io.BytesIO(body.encode("utf-8"))
    )


def test_infer_sends_json_schema_response_format(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHttp([chat_response('{"ok": true}')])
    monkeypatch.setattr(llm_providers.urllib.request, "urlopen", fake)
    provider = OpenAiCompatProvider("https://api.x.ai/v1", "xai-key")

    result = provider.infer("grok-4.5", "hello", SCHEMA, temperature=0.4, seed=7)

    url, body, headers = fake.requests[0]
    assert url == "https://api.x.ai/v1/chat/completions"
    assert body["model"] == "grok-4.5"
    assert body["temperature"] == 0.4
    assert body["seed"] == 7
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert headers["Authorization"] == "Bearer xai-key"
    assert result.response == {"ok": True}


def test_infer_falls_back_to_json_object_and_sticks(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHttp(
        [
            http_error(400, '{"error": "response_format json_schema unsupported"}'),
            chat_response('{"ok": true}'),
            chat_response('{"ok": false}'),
        ]
    )
    monkeypatch.setattr(llm_providers.urllib.request, "urlopen", fake)
    provider = OpenAiCompatProvider("https://api.x.ai/v1", "xai-key")

    first = provider.infer("grok-4.5", "hello", SCHEMA)
    second = provider.infer("grok-4.5", "again", SCHEMA)

    assert first.response == {"ok": True}
    assert second.response == {"ok": False}
    # request 2 and 3 use json_object mode with schema embedded in the prompt
    assert fake.requests[1][1]["response_format"] == {"type": "json_object"}
    assert "ok" in fake.requests[1][1]["messages"][1]["content"]
    # sticky: no wasted json_schema attempt on the second call
    assert len(fake.requests) == 3
    assert fake.requests[2][1]["response_format"] == {"type": "json_object"}


def test_infer_maps_http_errors_to_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHttp([http_error(429, "rate limited")])
    monkeypatch.setattr(llm_providers.urllib.request, "urlopen", fake)
    provider = OpenAiCompatProvider("https://api.x.ai/v1", "xai-key")

    with pytest.raises(ValueError, match="429"):
        provider.infer("grok-4.5", "hello", SCHEMA)


def test_available_models_parses_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHttp([{"data": [{"id": "grok-4.5"}, {"id": "grok-4"}]}])
    monkeypatch.setattr(llm_providers.urllib.request, "urlopen", fake)
    OpenAiCompatProvider._models_cache.clear()
    provider = OpenAiCompatProvider("https://api.x.ai/v1", "xai-key")

    assert provider.available_models() == ["grok-4.5", "grok-4"]
    assert provider.available_models() == ["grok-4.5", "grok-4"]  # served from cache
    assert len(fake.requests) == 1


def test_embed_is_not_supported() -> None:
    provider = OpenAiCompatProvider("https://api.x.ai/v1", "xai-key")
    with pytest.raises(ValueError, match="embeddings"):
        provider.embed(object())


def test_resolver_env_overrides_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)
    monkeypatch.setenv("ECHODRAFT_LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("ECHODRAFT_LLM_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setenv("ECHODRAFT_LLM_MODEL", "grok-4.5")
    monkeypatch.setenv("ECHODRAFT_LLM_API_KEY", "xai-env-key")
    monkeypatch.setenv("ECHODRAFT_LLM_CLOUD_CONSENT", "1")

    effective = resolve_effective_llm_settings(repo)

    assert effective.provider == "openai_compat"
    assert effective.model == "grok-4.5"
    assert effective.api_key == "xai-env-key"
    assert effective.cloud_consent is True
    assert set(effective.env_overrides) == {"provider", "baseUrl", "model", "apiKey", "cloudConsent"}


def test_ensure_cloud_ready_gates_consent_and_key() -> None:
    ensure_cloud_ready(
        EffectiveLlmSettings("ollama", None, None, None, False, ())
    )  # local always passes
    ready = EffectiveLlmSettings(
        "openai_compat", "https://api.x.ai/v1", "grok-4.5", "k", True, ()
    )
    ensure_cloud_ready(ready)
    for broken in (
        EffectiveLlmSettings("openai_compat", "https://api.x.ai/v1", "grok-4.5", "k", False, ()),
        EffectiveLlmSettings("openai_compat", "https://api.x.ai/v1", "grok-4.5", None, True, ()),
        EffectiveLlmSettings("openai_compat", None, "grok-4.5", "k", True, ()),
        EffectiveLlmSettings("openai_compat", "https://api.x.ai/v1", None, "k", True, ()),
    ):
        with pytest.raises(ValueError):
            ensure_cloud_ready(broken)
