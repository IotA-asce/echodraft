# Cloud LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optional cloud LLM providers via a generic OpenAI-compatible adapter (xAI + `grok-4.5` first), selected through DB-persisted settings with a hard consent gate, routing every generate call globally while embeddings stay on Ollama.

**Architecture:** A new leaf module `llm_providers.py` holds the OpenAI-compatible adapter, the effective-settings resolver (DB row merged with `ECHODRAFT_LLM_*` env overrides), and the consent guard; `LocalLlmService` picks its generate provider from those settings. A single-row `llm_settings` table (migration 0038) feeds three new API endpoints and a self-contained React settings card.

**Tech Stack:** FastAPI + Pydantic (`ApiModel`), SQLAlchemy + Alembic, urllib (no new deps), Next.js + TanStack Query.

**Spec:** `docs/specs/2026-07-10-cloud-llm-provider.md` (approved). Read it before starting.

## Global Constraints

- Local-first: with no configuration, behavior is byte-for-byte identical to today (provider `ollama`, per-stage models unchanged, existing cache keys keep their identity).
- Fail closed: cloud errors surface as `ValueError` through the existing `llm_runs`/checkpoint failure path. No silent fallback to Ollama.
- Consent gate is enforced in BOTH the PUT endpoint and `LocalLlmService.extract` (env-only setups included, via `ECHODRAFT_LLM_CLOUD_CONSENT`).
- The API key is never echoed by any endpoint — responses carry `hasApiKey` only.
- Embeddings always run on Ollama (`OpenAiCompatProvider.embed` raises).
- Repo workflow: work on branch `feat/cloud-llm-provider`, conventional commits ending `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`, never commit to `main`.
- Verification gate before merge: `uv run pytest`, `uv run ruff check .`, `uv run mypy apps/api/src libs/domain-models/src libs/db/src`, `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`, plus the disposable-DB alembic upgrade.

## Setup (before Task 1)

```bash
git checkout feat/cloud-llm-provider
git merge main   # fast-forwards: the branch tip (spec commit) is an ancestor of main
```

---

### Task 1: `llm_settings` table, migration 0038, repository

**Files:**
- Modify: `libs/db/src/echodraft_db/models.py` (append after `LlmRunRecord`, ~line 147)
- Create: `libs/db/alembic/versions/0038_llm_settings.py`
- Create: `libs/db/src/echodraft_db/llm_settings.py`
- Modify: `libs/db/src/echodraft_db/__init__.py`
- Test: `apps/api/tests/test_llm_settings.py`

**Interfaces:**
- Produces: `LlmSettingsRepository(database)` with
  `get() -> LlmSettingsRow` (auto-creates the default row) and
  `update(*, provider: str, base_url: str | None, model: str | None, api_key: str | None, cloud_consent: bool) -> LlmSettingsRow`.
  `LlmSettingsRow` is a frozen dataclass: `provider: str`, `base_url: str | None`, `model: str | None`, `api_key: str | None`, `cloud_consent: bool`, `updated_at: datetime | None`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/test_llm_settings.py
from echodraft_db import Database, LlmSettingsRepository


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/test_llm_settings.py -v`
Expected: FAIL — `ImportError: cannot import name 'LlmSettingsRepository'`

- [ ] **Step 3: Implement record, migration, repository, exports**

Append to `libs/db/src/echodraft_db/models.py` (after `LlmRunRecord`):

```python
class LlmSettingsRecord(Base):
    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="ollama")
    base_url: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(200))
    api_key: Mapped[str | None] = mapped_column(Text)
    cloud_consent: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Create `libs/db/alembic/versions/0038_llm_settings.py`:

```python
"""add llm provider settings"""

from alembic import op
import sqlalchemy as sa

revision = "0038_llm_settings"
down_revision = "0037_sound_planner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="ollama"),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("cloud_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("llm_settings")
```

Create `libs/db/src/echodraft_db/llm_settings.py`:

```python
from dataclasses import dataclass
from datetime import UTC, datetime

from .database import Database
from .models import LlmSettingsRecord

_SINGLETON_ID = 1


@dataclass(frozen=True)
class LlmSettingsRow:
    provider: str
    base_url: str | None
    model: str | None
    api_key: str | None
    cloud_consent: bool
    updated_at: datetime | None


def _row(record: LlmSettingsRecord) -> LlmSettingsRow:
    return LlmSettingsRow(
        provider=record.provider,
        base_url=record.base_url,
        model=record.model,
        api_key=record.api_key,
        cloud_consent=record.cloud_consent,
        updated_at=record.updated_at,
    )


class LlmSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self) -> LlmSettingsRow:
        with self.database.session() as session:
            record = session.get(LlmSettingsRecord, _SINGLETON_ID)
            if record is None:
                record = LlmSettingsRecord(id=_SINGLETON_ID, provider="ollama", cloud_consent=False)
                session.add(record)
                session.commit()
            return _row(record)

    def update(
        self,
        *,
        provider: str,
        base_url: str | None,
        model: str | None,
        api_key: str | None,
        cloud_consent: bool,
    ) -> LlmSettingsRow:
        with self.database.session() as session:
            record = session.get(LlmSettingsRecord, _SINGLETON_ID)
            if record is None:
                record = LlmSettingsRecord(id=_SINGLETON_ID)
                session.add(record)
            record.provider = provider
            record.base_url = base_url
            record.model = model
            record.api_key = api_key
            record.cloud_consent = cloud_consent
            record.updated_at = datetime.now(UTC)
            session.commit()
            return _row(record)
```

In `libs/db/src/echodraft_db/__init__.py`: add `from .llm_settings import LlmSettingsRepository, LlmSettingsRow` and append both names to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_llm_settings.py apps/api/tests/test_migrations.py -v`
Expected: PASS (migration test walks the chain and must accept 0038)

- [ ] **Step 5: Commit**

```bash
git add libs/db apps/api/tests/test_llm_settings.py
git commit -m "feat(db): llm provider settings table, migration 0038, repository"
```

---

### Task 2: Provider module — adapter, resolver, consent guard

**Files:**
- Create: `apps/api/src/echodraft_api/llm_providers.py`
- Modify: `apps/api/src/echodraft_api/local_llm.py` (move JSON-parse helpers out; re-export for compat)
- Test: `apps/api/tests/test_llm_providers.py`

**Interfaces:**
- Produces (all in `echodraft_api.llm_providers`):
  - `GenerateResult` — frozen dataclass `response: dict[str, object]`, `raw: dict[str, object]` (same shape `OllamaGenerateResult` had; `local_llm.OllamaGenerateResult` becomes an alias so existing imports keep working).
  - `parse_llm_json_object(response: str) -> dict[str, object]` — MOVED here from `local_llm.py` verbatim, together with `_strip_thinking_blocks`, `_strip_markdown_json_fence`, `_balanced_json_object_candidates`. `local_llm.py` re-exports `parse_llm_json_object`.
  - `OpenAiCompatProvider(base_url: str, api_key: str, name: str = "cloud")` with
    `infer(model, prompt, schema, *, temperature=None, seed=None) -> GenerateResult`,
    `available_models(*, use_cache: bool = True) -> list[str]`,
    `embed(request) -> NoReturn` (raises `ValueError`).
  - `EffectiveLlmSettings` — frozen dataclass `provider: str`, `base_url: str | None`, `model: str | None`, `api_key: str | None`, `cloud_consent: bool`, `env_overrides: tuple[str, ...]`.
  - `resolve_effective_llm_settings(repo: LlmSettingsRepository) -> EffectiveLlmSettings` — DB row, then env overrides `ECHODRAFT_LLM_PROVIDER`, `ECHODRAFT_LLM_BASE_URL`, `ECHODRAFT_LLM_MODEL`, `ECHODRAFT_LLM_API_KEY`, `ECHODRAFT_LLM_CLOUD_CONSENT` (truthy: `1/true/yes`); `env_overrides` lists the field names that came from env (`"provider"`, `"baseUrl"`, `"model"`, `"apiKey"`, `"cloudConsent"`).
  - `ensure_cloud_ready(settings: EffectiveLlmSettings) -> None` — raises `ValueError` unless provider is `"ollama"` OR (`cloud_consent` and `api_key` and `base_url` and `model`).

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/test_llm_providers.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_llm_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'echodraft_api.llm_providers'`

- [ ] **Step 3: Implement `llm_providers.py` and slim `local_llm.py`**

Create `apps/api/src/echodraft_api/llm_providers.py`:

```python
"""LLM provider adapters and provider-selection settings.

This module is a leaf (imports no other echodraft_api modules) so both
``local_llm`` and ``main`` can build on it without cycles.
"""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, NoReturn, cast

if TYPE_CHECKING:
    from echodraft_db import LlmSettingsRepository

_ENV_TRUTHY = {"1", "true", "yes"}

SYSTEM_JSON_INSTRUCTION = (
    "Return exactly one JSON object that satisfies the supplied JSON schema. "
    "Do not include markdown, commentary, or reasoning text."
)


@dataclass(frozen=True)
class GenerateResult:
    response: dict[str, object]
    raw: dict[str, object]


@dataclass(frozen=True)
class EffectiveLlmSettings:
    provider: str
    base_url: str | None
    model: str | None
    api_key: str | None
    cloud_consent: bool
    env_overrides: tuple[str, ...]


def resolve_effective_llm_settings(repo: "LlmSettingsRepository") -> EffectiveLlmSettings:
    row = repo.get()
    overrides: list[str] = []
    provider = row.provider
    base_url = row.base_url
    model = row.model
    api_key = row.api_key
    cloud_consent = row.cloud_consent
    if value := os.getenv("ECHODRAFT_LLM_PROVIDER"):
        provider = value.strip().lower()
        overrides.append("provider")
    if value := os.getenv("ECHODRAFT_LLM_BASE_URL"):
        base_url = value.strip()
        overrides.append("baseUrl")
    if value := os.getenv("ECHODRAFT_LLM_MODEL"):
        model = value.strip()
        overrides.append("model")
    if value := os.getenv("ECHODRAFT_LLM_API_KEY"):
        api_key = value
        overrides.append("apiKey")
    if (value := os.getenv("ECHODRAFT_LLM_CLOUD_CONSENT")) is not None:
        cloud_consent = value.strip().lower() in _ENV_TRUTHY
        overrides.append("cloudConsent")
    return EffectiveLlmSettings(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        cloud_consent=cloud_consent,
        env_overrides=tuple(overrides),
    )


def ensure_cloud_ready(settings: EffectiveLlmSettings) -> None:
    if settings.provider == "ollama":
        return
    if not settings.cloud_consent:
        raise ValueError(
            "Cloud LLM provider is configured without consent. Acknowledge that manuscript "
            "text will be sent to the provider (settings UI or ECHODRAFT_LLM_CLOUD_CONSENT=1)."
        )
    if not settings.api_key:
        raise ValueError("Cloud LLM provider requires an API key.")
    if not settings.base_url:
        raise ValueError("Cloud LLM provider requires a base URL.")
    if not settings.model:
        raise ValueError("Cloud LLM provider requires a model.")


class OpenAiCompatProvider:
    """OpenAI-compatible chat-completions adapter (xAI, OpenAI, OpenRouter, vLLM...).

    Fails closed: every transport or protocol problem raises ``ValueError`` so the
    caller's existing llm_runs/checkpoint failure path applies unchanged.
    """

    _models_cache: ClassVar[dict[str, list[str]]] = {}

    def __init__(self, base_url: str, api_key: str, name: str = "cloud") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = name
        self._force_json_object = False

    def infer(
        self,
        model: str,
        prompt: str,
        schema: dict[str, object],
        *,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> GenerateResult:
        attempts = ["json_object"] if self._force_json_object else ["json_schema", "json_object"]
        last_error: ValueError | None = None
        for mode in attempts:
            user_prompt = prompt
            if mode == "json_object":
                user_prompt = (
                    f"{prompt}\n\nReturn only a JSON object matching this JSON schema:\n"
                    f"{json.dumps(schema)}"
                )
            body: dict[str, object] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_JSON_INSTRUCTION},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": (
                    {
                        "type": "json_schema",
                        "json_schema": {"name": "extraction", "schema": schema, "strict": True},
                    }
                    if mode == "json_schema"
                    else {"type": "json_object"}
                ),
                "temperature": 0 if temperature is None else temperature,
                "max_tokens": 4096,
                "stream": False,
            }
            if seed is not None:
                body["seed"] = seed
            try:
                payload = self._request("POST", "/chat/completions", body, timeout=180)
            except _RetryableSchemaMode as error:
                self._force_json_object = True
                last_error = ValueError(str(error))
                continue
            content = _chat_content(payload)
            return GenerateResult(response=parse_llm_json_object(content), raw=payload)
        raise last_error or ValueError(f"{self.name} inference failed.")

    def available_models(self, *, use_cache: bool = True) -> list[str]:
        if use_cache and self.base_url in self._models_cache:
            return self._models_cache[self.base_url]
        payload = self._request("GET", "/models", None, timeout=30)
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError(f"{self.name} /models returned an unexpected response.")
        models = [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
        self._models_cache[self.base_url] = models
        return models

    def embed(self, request: object) -> NoReturn:
        raise ValueError(
            f"{self.name} provider does not serve embeddings; embeddings always run on Ollama."
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None,
        timeout: int,
    ) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8", errors="replace")[:500]
            except OSError:
                pass
            if error.code == 400 and path == "/chat/completions" and not self._force_json_object:
                raise _RetryableSchemaMode(
                    f"{self.name} rejected structured output (HTTP 400): {detail}"
                ) from error
            raise ValueError(
                f"{self.name} request failed for {path}: HTTP {error.code} {detail}"
            ) from error
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ValueError(f"{self.name} request failed for {path}: {error}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"{self.name} returned non-object JSON for {path}.")
        return cast(dict[str, object], parsed)


class _RetryableSchemaMode(Exception):
    """HTTP 400 on a json_schema attempt — retry once in json_object mode."""


def _chat_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = cast(dict[str, object], choices[0]).get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
    raise ValueError("Chat completion response did not include message content.")


def parse_llm_json_object(response: str) -> dict[str, object]:
    cleaned = _strip_thinking_blocks(response).strip()
    candidates = [cleaned, *_balanced_json_object_candidates(cleaned)]
    for candidate in candidates:
        try:
            parsed = json.loads(_strip_markdown_json_fence(candidate))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    raise ValueError("LLM response was not valid JSON.")


def _strip_thinking_blocks(response: str) -> str:
    return re.sub(r"<think\b[^>]*>.*?</think>", "", response, flags=re.IGNORECASE | re.DOTALL)


def _strip_markdown_json_fence(response: str) -> str:
    stripped = response.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else stripped


def _balanced_json_object_candidates(response: str) -> list[str]:
    candidates: list[str] = []
    depth = 0
    start: int | None = None
    in_string = False
    escaped = False

    for index, char in enumerate(response):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(response[start : index + 1])
                start = None

    return candidates
```

In `apps/api/src/echodraft_api/local_llm.py`:

1. DELETE the local definitions of `parse_llm_json_object`, `_strip_thinking_blocks`, `_strip_markdown_json_fence`, `_balanced_json_object_candidates`, and the `OllamaGenerateResult` dataclass (and the now-unused `re` import).
2. Add near the top:

```python
from .llm_providers import GenerateResult, parse_llm_json_object

# Backwards-compatible aliases: the dataclass and parser moved to llm_providers.
OllamaGenerateResult = GenerateResult

__all__ = [
    "CheckpointContext",
    "DEFAULT_EXTRACTION_SCHEMA",
    "LocalLlmService",
    "OllamaGenerateResult",
    "OllamaLlmProvider",
    "OllamaProvider",
    "SchemaValidationError",
    "parse_llm_json_object",
    "validate_json_schema",
]
```

3. The one behavioral nit: `parse_llm_json_object`'s failure message changes from "Ollama response was not valid JSON." to "LLM response was not valid JSON." — grep tests for the old string and update if any assert on it:
   `grep -rn "Ollama response was not valid JSON" apps/api/tests`

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_llm_providers.py apps/api/tests/test_local_llm.py -v`
Expected: PASS (both the new module and all existing local_llm tests via the aliases)

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/echodraft_api/llm_providers.py apps/api/src/echodraft_api/local_llm.py apps/api/tests/test_llm_providers.py
git commit -m "feat(api): OpenAI-compatible provider adapter, effective-settings resolver, consent guard"
```

---

### Task 3: Route `LocalLlmService` through the effective provider

**Files:**
- Modify: `apps/api/src/echodraft_api/local_llm.py` (`LocalLlmService.__init__` ~line 180, `extract` ~line 188, `embed` ~line 368, `_require_model` ~line 372, `_inference_cache_key` ~line 426)
- Modify: `apps/api/src/echodraft_api/container.py` (add `llm_settings` field + wiring)
- Test: `apps/api/tests/test_local_llm.py` (append)

**Interfaces:**
- Consumes: Task 1 `LlmSettingsRepository`; Task 2 resolver/guard/adapter.
- Produces: `container.llm_settings: LlmSettingsRepository`. `LocalLlmService` gains attributes `effective: EffectiveLlmSettings`, `provider_name: str` (`"ollama"` | `"openai_compat"`), and `ollama: OllamaLlmProvider` (embeds). `_inference_cache_key(...)` gains keyword `provider: str | None = None`.

- [ ] **Step 1: Write the failing tests** (append to `apps/api/tests/test_llm_settings.py`)

```python
import pytest

import echodraft_api.local_llm as local_llm
from echodraft_api.llm_providers import OpenAiCompatProvider
from echodraft_api.local_llm import _inference_cache_key


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
```

Note on helpers: the `client` fixture comes from `apps/api/tests/conftest.py`
(already exists — temp SQLite + TestClient). Copy the two small module-level
helpers `wait_for_job(client, job_id)` and `project_with_source(client)`
verbatim from `apps/api/tests/test_local_llm.py` (lines 10–29) into
`test_llm_settings.py` — test modules in this suite do not import from each
other.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_llm_settings.py -v`
Expected: FAIL — `TypeError: _inference_cache_key() got an unexpected keyword argument 'provider'` and cloud tests fail because the service ignores the env.

- [ ] **Step 3: Implement service routing**

`container.py`: import `LlmSettingsRepository` from `echodraft_db`, add field `llm_settings: LlmSettingsRepository` to `AppContainer`, and pass `llm_settings=LlmSettingsRepository(database)` in `build_container` (alongside `llm_runs=` at line ~113).

`local_llm.py` — replace `LocalLlmService.__init__`:

```python
class LocalLlmService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.ollama = OllamaProvider(container.settings.ollama_base_url)
        self.effective = resolve_effective_llm_settings(container.llm_settings)
        if self.effective.provider != "ollama":
            self.provider_name = "openai_compat"
            self.provider: OllamaLlmProvider | OpenAiCompatProvider = OpenAiCompatProvider(
                self.effective.base_url or "", self.effective.api_key or ""
            )
        else:
            self.provider_name = "ollama"
            self.provider = self.ollama
```

(imports: `from .llm_providers import EffectiveLlmSettings, GenerateResult, OpenAiCompatProvider, ensure_cloud_ready, parse_llm_json_object, resolve_effective_llm_settings`)

In `extract(...)` make these exact changes:

1. Right after the `project` lookup, add the routing and the belt-and-braces gate:

```python
        effective_model = request.model
        if self.provider_name != "ollama":
            ensure_cloud_ready(self.effective)
            effective_model = self.effective.model or request.model
```

2. Replace every use of `request.model` below that point with `effective_model`:
   `self._require_model(request.model)` → `self._require_model(effective_model)`;
   `llm_runs.create(..., provider="ollama", model=request.model, ...)` →
   `provider=self.provider_name, model=effective_model`;
   the cache key call becomes:

```python
        cache_key = _inference_cache_key(
            effective_model,
            request.task,
            prompt,
            schema,
            request.temperature,
            request.seed,
            provider=self.provider_name,
        )
```

   `put_cache(..., model_id=request.model, ...)` → `model_id=effective_model`;
   and both `self.provider.infer(request.model, ...)` calls → `self.provider.infer(effective_model, ...)`.

3. `embed(...)` must keep using Ollama regardless of the active provider:

```python
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self._require_ollama_model(request.model)
        return self.ollama.embed(request)
```

4. Split `_require_model` so each provider checks its own catalog:

```python
    def _require_model(self, model: str) -> None:
        if self.provider_name == "ollama":
            self._require_ollama_model(model)
            return
        provider = cast(OpenAiCompatProvider, self.provider)
        if model not in provider.available_models():
            raise ValueError(
                f"Model {model} is not served by the configured cloud endpoint."
            )

    def _require_ollama_model(self, model: str) -> None:
        models = self.ollama.tags()
        if not find_ollama_model(models, model):
            raise ValueError(f"Ollama model {model} is not installed. Pull it in Model Center first.")
```

5. `installed_models()` keeps returning Ollama tags: change `self.provider.tags()` → `self.ollama.tags()`.

6. `_inference_cache_key` — add the provider field without disturbing local identity:

```python
def _inference_cache_key(
    model: str,
    task: str,
    prompt: str,
    schema: dict[str, object],
    temperature: float | None = None,
    seed: int | None = None,
    *,
    provider: str | None = None,
) -> str:
    payload = {
        "model": model,
        "task": task,
        "prompt": prompt,
        "schema": schema,
        "temperature": temperature,
        "seed": seed,
    }
    # Cloud draws get their own cache namespace. Local Ollama calls keep the
    # historical payload shape so existing cache entries and checkpoint
    # output_refs keep their identity.
    if provider and provider != "ollama":
        payload["provider"] = provider
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"llm.generate:{digest}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_llm_settings.py apps/api/tests/test_local_llm.py apps/api/tests/test_resume.py -v`
Expected: PASS. Then run the full backend suite to catch any consumer that
constructed `LocalLlmService` in an unexpected way:
`uv run pytest` — expected: all pass (322+ passed, 2 skipped).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/echodraft_api/local_llm.py apps/api/src/echodraft_api/container.py apps/api/tests/test_llm_settings.py
git commit -m "feat(api): route all LLM generate calls through the configured provider"
```

---

### Task 4: Domain models + settings API endpoints

**Files:**
- Modify: `libs/domain-models/src/echodraft_domain/models.py` (append after `EmbeddingResult`, ~line 292)
- Modify: `libs/domain-models/src/echodraft_domain/__init__.py` (export the four new names)
- Modify: `apps/api/src/echodraft_api/main.py` (after the llm-runs endpoints, ~line 650)
- Test: `apps/api/tests/test_llm_settings.py` (append)

**Interfaces:**
- Consumes: Task 1 repository, Task 2 resolver/adapter.
- Produces (in `echodraft_domain`):

```python
class LlmProviderSettings(ApiModel):
    provider: str = "ollama"
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None
    cloud_consent: bool = Field(default=False, alias="cloudConsent")
    has_api_key: bool = Field(default=False, alias="hasApiKey")
    env_overrides: list[str] = Field(default_factory=list, alias="envOverrides")


class LlmProviderSettingsUpdate(ApiModel):
    provider: str
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None
    # None = keep the stored key; "" = clear it; any other string replaces it.
    api_key: str | None = Field(default=None, alias="apiKey")
    cloud_consent: bool = Field(default=False, alias="cloudConsent")


class LlmConnectionTestRequest(ApiModel):
    base_url: str = Field(alias="baseUrl")
    # None = use the stored/env key.
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None


class LlmConnectionTestResult(ApiModel):
    ok: bool
    models: list[str] = Field(default_factory=list)
    model_found: bool | None = Field(default=None, alias="modelFound")
    error: str | None = None
```

- Endpoints: `GET /api/v1/llm/settings`, `PUT /api/v1/llm/settings`, `POST /api/v1/llm/settings/test`.

- [ ] **Step 1: Write the failing tests** (append to `apps/api/tests/test_llm_settings.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest apps/api/tests/test_llm_settings.py -v`
Expected: FAIL — 404s (endpoints missing).

- [ ] **Step 3: Implement models and endpoints**

Add the four models above to `libs/domain-models/src/echodraft_domain/models.py` and export them from `__init__.py` (follow the existing alphabetical import/`__all__` pattern).

In `apps/api/src/echodraft_api/main.py`, import
`LlmProviderSettings, LlmProviderSettingsUpdate, LlmConnectionTestRequest, LlmConnectionTestResult` from `echodraft_domain` and
`OpenAiCompatProvider, resolve_effective_llm_settings` from `.llm_providers`,
then add after the `get_llm_run` endpoint:

```python
    def _llm_settings_response(container: AppContainer) -> LlmProviderSettings:
        effective = resolve_effective_llm_settings(container.llm_settings)
        return LlmProviderSettings.model_validate(
            {
                "provider": effective.provider,
                "baseUrl": effective.base_url,
                "model": effective.model,
                "cloudConsent": effective.cloud_consent,
                "hasApiKey": bool(effective.api_key),
                "envOverrides": list(effective.env_overrides),
            }
        )

    @app.get("/api/v1/llm/settings", response_model=LlmProviderSettings)
    def get_llm_settings(request: Request) -> LlmProviderSettings:
        return _llm_settings_response(request.app.state.container)

    @app.put("/api/v1/llm/settings", response_model=LlmProviderSettings)
    def update_llm_settings(
        payload: LlmProviderSettingsUpdate, request: Request
    ) -> LlmProviderSettings:
        container: AppContainer = request.app.state.container
        if payload.provider not in {"ollama", "openai_compat"}:
            raise HTTPException(status_code=422, detail="Unknown LLM provider.")
        stored = container.llm_settings.get()
        if payload.api_key is None:
            effective_key = stored.api_key
        elif payload.api_key == "":
            effective_key = None
        else:
            effective_key = payload.api_key
        if payload.provider == "openai_compat":
            if not payload.cloud_consent:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Cloud providers require explicit consent: manuscript text will be "
                        "sent to the provider's servers."
                    ),
                )
            if not (effective_key or os.getenv("ECHODRAFT_LLM_API_KEY")):
                raise HTTPException(status_code=422, detail="Cloud providers require an API key.")
            if not payload.base_url or not payload.model:
                raise HTTPException(
                    status_code=422, detail="Cloud providers require a base URL and a model."
                )
        container.orchestrator_pools.writer.run(
            lambda: container.llm_settings.update(
                provider=payload.provider,
                base_url=payload.base_url,
                model=payload.model,
                api_key=effective_key,
                cloud_consent=payload.cloud_consent,
            )
        )
        return _llm_settings_response(container)

    @app.post("/api/v1/llm/settings/test", response_model=LlmConnectionTestResult)
    def test_llm_connection(
        payload: LlmConnectionTestRequest, request: Request
    ) -> LlmConnectionTestResult:
        container: AppContainer = request.app.state.container
        key = payload.api_key
        if key is None:
            key = resolve_effective_llm_settings(container.llm_settings).api_key
        provider = OpenAiCompatProvider(payload.base_url, key or "")
        try:
            models = provider.available_models(use_cache=False)
        except ValueError as error:
            return LlmConnectionTestResult(ok=False, models=[], model_found=None, error=str(error))
        found = payload.model in models if payload.model else None
        return LlmConnectionTestResult(ok=True, models=models, model_found=found, error=None)
```

(`main.py` already imports `os`; if not, add it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest apps/api/tests/test_llm_settings.py -v` — expected: PASS.
Then: `uv run ruff check . && uv run mypy apps/api/src libs/domain-models/src libs/db/src` — expected: clean.

- [ ] **Step 5: Commit**

```bash
git add libs/domain-models apps/api/src/echodraft_api/main.py apps/api/tests/test_llm_settings.py
git commit -m "feat(api): LLM provider settings endpoints with consent gate and key masking"
```

---

### Task 5: Dashboard — AI Provider card

**Files:**
- Modify: `apps/web/app/api.ts` (append types + calls)
- Create: `apps/web/app/components/setup/AiProviderCard.tsx`
- Modify: `apps/web/app/project-dashboard.tsx` (mount the card next to the Model Center drawer, ~line 2287)

**Interfaces:**
- Consumes: Task 4 endpoints.
- Produces: `getLlmSettings()`, `updateLlmSettings(payload)`, `testLlmConnection(payload)` in `api.ts`; `<AiProviderCard />` self-contained component (fetches its own data via TanStack Query — no props).

- [ ] **Step 1: Add API client functions** (append to `apps/web/app/api.ts`)

```ts
export type LlmProviderSettings = {
  provider: string;
  baseUrl: string | null;
  model: string | null;
  cloudConsent: boolean;
  hasApiKey: boolean;
  envOverrides: string[];
};
export type LlmConnectionTest = {
  ok: boolean;
  models: string[];
  modelFound: boolean | null;
  error: string | null;
};
export const getLlmSettings = () => request<LlmProviderSettings>(`/api/v1/llm/settings`);
export const updateLlmSettings = (payload: {
  provider: string;
  baseUrl: string | null;
  model: string | null;
  apiKey?: string;
  cloudConsent: boolean;
}) => request<LlmProviderSettings>(`/api/v1/llm/settings`, json("PUT", payload));
export const testLlmConnection = (payload: { baseUrl: string; apiKey?: string; model?: string }) =>
  request<LlmConnectionTest>(`/api/v1/llm/settings/test`, json("POST", payload));
```

- [ ] **Step 2: Create the card component**

`apps/web/app/components/setup/AiProviderCard.tsx` (reuse the monochrome
classes already used by `ModelCenter.tsx` — `studio-card`, `model-badge`,
`small-button` — and follow the surrounding form-field markup conventions in
`project-dashboard.tsx`; check how it renders labeled inputs and reuse those
class names rather than inventing new CSS):

```tsx
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getLlmSettings,
  testLlmConnection,
  updateLlmSettings,
  type LlmConnectionTest,
} from "../../api";

const XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1";
const XAI_DEFAULT_MODEL = "grok-4.5";

export function AiProviderCard() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["llm-settings"], queryFn: getLlmSettings });
  const [draft, setDraft] = useState<{
    provider: string;
    baseUrl: string;
    model: string;
    apiKey: string;
    cloudConsent: boolean;
  } | null>(null);
  const [testResult, setTestResult] = useState<LlmConnectionTest | null>(null);

  const save = useMutation({
    mutationFn: updateLlmSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-settings"], data);
      setDraft(null);
      setTestResult(null);
    },
  });
  const test = useMutation({ mutationFn: testLlmConnection, onSuccess: setTestResult });

  if (settings.isPending) return <article className="studio-card">Loading AI provider…</article>;
  if (settings.isError) {
    return <article className="studio-card">AI provider settings unavailable.</article>;
  }
  const current = settings.data;
  const form = draft ?? {
    provider: current.provider,
    baseUrl: current.baseUrl ?? XAI_DEFAULT_BASE_URL,
    model: current.model ?? XAI_DEFAULT_MODEL,
    apiKey: "",
    cloudConsent: current.cloudConsent,
  };
  const isCloud = form.provider === "openai_compat";
  const canSave =
    !save.isPending &&
    (!isCloud || (form.cloudConsent && (form.apiKey !== "" || current.hasApiKey)));

  return (
    <article className="studio-card ai-provider-card">
      <div className="model-card-heading">
        <div>
          <strong>AI Provider</strong>
          <small>Book understanding: structure, characters, attribution, direction</small>
        </div>
        <span className={`model-badge ${current.provider === "ollama" ? "ready" : "info"}`}>
          {current.provider === "ollama" ? "local · ollama" : `cloud · ${current.model ?? "?"}`}
        </span>
      </div>
      {current.envOverrides.length > 0 ? (
        <small>Environment overrides active: {current.envOverrides.join(", ")}</small>
      ) : null}
      <label>
        Provider
        <select
          value={form.provider}
          onChange={(e) => setDraft({ ...form, provider: e.target.value })}
        >
          <option value="ollama">Local (Ollama)</option>
          <option value="openai_compat">Cloud (OpenAI-compatible, e.g. xAI)</option>
        </select>
      </label>
      {isCloud ? (
        <>
          <label>
            Base URL
            <input
              type="text"
              value={form.baseUrl}
              onChange={(e) => setDraft({ ...form, baseUrl: e.target.value })}
            />
          </label>
          <label>
            Model
            <input
              type="text"
              value={form.model}
              onChange={(e) => setDraft({ ...form, model: e.target.value })}
            />
          </label>
          <label>
            API key {current.hasApiKey ? <small>(saved — leave blank to keep)</small> : null}
            <input
              type="password"
              value={form.apiKey}
              placeholder={current.hasApiKey ? "••••••••" : "xai-…"}
              onChange={(e) => setDraft({ ...form, apiKey: e.target.value })}
            />
          </label>
          <label className="consent-row">
            <input
              type="checkbox"
              checked={form.cloudConsent}
              onChange={(e) => setDraft({ ...form, cloudConsent: e.target.checked })}
            />
            <span>
              I understand manuscript text will be sent to this provider&apos;s servers.
              Echodraft remains local-first; this is strictly opt-in.
            </span>
          </label>
          <div className="model-actions">
            <button
              type="button"
              className="small-button"
              disabled={test.isPending || !form.baseUrl}
              onClick={() =>
                test.mutate({
                  baseUrl: form.baseUrl,
                  ...(form.apiKey ? { apiKey: form.apiKey } : {}),
                  ...(form.model ? { model: form.model } : {}),
                })
              }
            >
              Test connection
            </button>
          </div>
          {testResult ? (
            <small role="status">
              {testResult.ok
                ? `Connected. ${testResult.models.length} models${
                    testResult.modelFound === false ? ` — ${form.model} NOT found` : ""
                  }${testResult.modelFound ? ` — ${form.model} available` : ""}`
                : `Connection failed: ${testResult.error}`}
            </small>
          ) : null}
        </>
      ) : null}
      <div className="model-actions">
        <button
          type="button"
          className="small-button"
          disabled={!canSave}
          onClick={() =>
            save.mutate({
              provider: form.provider,
              baseUrl: isCloud ? form.baseUrl : null,
              model: isCloud ? form.model : null,
              ...(form.apiKey !== "" ? { apiKey: form.apiKey } : {}),
              cloudConsent: isCloud ? form.cloudConsent : false,
            })
          }
        >
          {save.isPending ? "Saving…" : "Save provider"}
        </button>
        {save.isError ? <small role="alert">{String(save.error)}</small> : null}
      </div>
    </article>
  );
}
```

- [ ] **Step 3: Mount it**

In `apps/web/app/project-dashboard.tsx`: add
`import { AiProviderCard } from "./components/setup/AiProviderCard";` next to the
`ModelCenter` import (~line 129), and render `<AiProviderCard />` immediately
after the Model Center `<Drawer …>` element (~line 2288), inside the same
parent container.

- [ ] **Step 4: Verify the web gate**

Run: `npm run web:lint && npm run web:typecheck && npm run web:test:smoke`
Expected: all pass (smoke needs `npx playwright install chromium` once). The
card must not break smoke when the API is absent — the `isError` branch
renders a plain card, no crash.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/api.ts apps/web/app/components/setup/AiProviderCard.tsx apps/web/app/project-dashboard.tsx
git commit -m "feat(web): AI provider settings card with consent gate and connection test"
```

---

### Task 6: Docs, migration check, full gate, merge

**Files:**
- Create: `docs/architecture/local-ai/cloud-llm-providers.md`
- Modify: `docs/README.md` (architecture `local-ai/` entry), `README.md` (privacy copy), `docs/progress-tracker.md` (new entry)

**Interfaces:** none — documentation and verification.

- [ ] **Step 1: Write `docs/architecture/local-ai/cloud-llm-providers.md`**

Content requirements (write it, not placeholders): what the provider layer is
(one `OpenAiCompatProvider` for any OpenAI-compatible endpoint; xAI/grok-4.5 is
the first-class default), the settings model (DB single row, `ECHODRAFT_LLM_*`
env overrides, key never echoed), the consent gate (both enforcement points),
routing semantics (global model override; per-stage defaults apply only to
Ollama; embeddings always Ollama), failure semantics (fail closed, resumable),
cache-key namespacing (provider field added only for cloud), and the three API
endpoints with example payloads. Link to `docs/specs/2026-07-10-cloud-llm-provider.md`.

- [ ] **Step 2: Update the doc set**

- `docs/README.md`: in the Directory map architecture bullet, extend the
  `local-ai/` list with `[cloud-llm-providers](architecture/local-ai/cloud-llm-providers.md)`.
- Root `README.md`: adjust the three absolute privacy claims to stay honest —
  line 21 ("Everything runs on your hardware…") gains: cloud LLM providers are
  available strictly opt-in behind a consent gate; the comparison-table row
  "Cloud-first, upload your book" / "Local-first, nothing leaves your machine"
  becomes "Local-first — nothing leaves your machine unless you explicitly opt
  in to a cloud LLM"; the "Local-first, forever." vision bullet gains
  "Optional bring-your-own-key cloud LLM providers exist today — strictly
  opt-in, never required."
- `docs/progress-tracker.md`: append a dated entry recording the feature, its
  branch, and the verification evidence.

- [ ] **Step 3: Run the migration check and the full gate**

```bash
mkdir -p .tmp
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db uv run alembic -c libs/db/alembic.ini upgrade head
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
npm run web:lint
npm run web:typecheck
npm run web:test:smoke
```

Expected: migration reaches `0038_llm_settings`; every gate green.

- [ ] **Step 4: Commit docs, merge, push**

```bash
git add docs README.md
git commit -m "docs: cloud LLM provider architecture doc, honest privacy copy, tracker entry"
git checkout main
git merge --no-ff feat/cloud-llm-provider -m "merge: optional cloud LLM providers (xAI/grok-4.5 first)"
git push origin main feat/cloud-llm-provider
```

(Every commit message ends with the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer per repo rules.)

---

## Out of scope (do NOT implement)

- Chunk-size tuning for large-context cloud models (V3 follow-up).
- Per-stage provider routing, multiple named provider profiles, Anthropic-native adapters, OS-keyring storage, cost/token accounting.
- Retry-with-backoff / job-pause on rate limits (fail closed is the contract).
