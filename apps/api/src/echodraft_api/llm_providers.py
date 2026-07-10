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
