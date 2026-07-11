# Cloud LLM Providers

Echodraft is local-first: with no configuration, every LLM generate call runs
against local Ollama and nothing leaves the machine. This document describes
the **optional, strictly opt-in** cloud provider layer that can route those
same generate calls to any OpenAI-compatible endpoint — the first-class target
is the xAI API with `grok-4.5`.

Approved design spec: [specs/2026-07-10-cloud-llm-provider.md](../../specs/2026-07-10-cloud-llm-provider.md).
Companion doc for the local baseline: [local-llm-service.md](local-llm-service.md).

## The provider layer

There is exactly one cloud adapter: `OpenAiCompatProvider`
(`apps/api/src/echodraft_api/llm_providers.py`). It speaks the OpenAI
chat-completions dialect, so a single implementation covers xAI, OpenAI,
OpenRouter, vLLM, and anything else exposing `/chat/completions` + `/models`.
There are no per-vendor adapters; xAI is simply the pre-filled default in the
UI (`https://api.x.ai/v1`, `grok-4.5`).

The adapter implements the same narrow surface `LocalLlmService` consumes from
the Ollama provider:

- `infer(model, prompt, schema, *, temperature=None, seed=None)` —
  `POST {base_url}/chat/completions` with a fixed system message ("return
  exactly one JSON object…") and
  `response_format: {"type": "json_schema", "json_schema": {..., "strict": true}}`.
  `temperature` defaults to 0 (matching the deterministic Ollama default),
  `seed` maps to the OpenAI-compatible `seed` field, `max_tokens` is 4096, and
  the request timeout is 180 s.
  - **Structured-output fallback:** if the endpoint rejects `json_schema`
    (HTTP 400 on `/chat/completions`), the adapter retries once with
    `{"type": "json_object"}` and the schema embedded in the prompt, and the
    fallback is **sticky** on the provider instance — the first 400 flips a
    flag so subsequent calls skip the failing mode instead of paying a failed
    request every time.
  - Response content flows through the shared `parse_llm_json_object`
    (thinking-block stripping, fence stripping, balanced-object recovery);
    schema validation and the two-attempt repair loop stay in
    `LocalLlmService.extract`, above the provider.
- `available_models(*, use_cache=True)` — `GET {base_url}/models`, cached per
  `base_url` so per-unit extraction calls do not pay a network round trip.
  The test-connection endpoint passes `use_cache=False` to always hit the
  network.
- `embed(...)` — always raises `ValueError`. **Embeddings never go to the
  cloud**; see routing below.

Transport is stdlib `urllib` with `Authorization: Bearer <key>` — no new
dependency, matching the Ollama adapter.

## Settings model

Settings live in a **single-row `llm_settings` table** (Alembic migration
`0038_llm_settings`): `provider` (`"ollama"` | `"openai_compat"`), `base_url`,
`model`, `api_key`, `cloud_consent`, `updated_at`. Access goes through
`LlmSettingsRepository` in `libs/db`; writes run on the shared writer pool.

`resolve_effective_llm_settings` merges the DB row with read-time environment
overrides (for CI/headless use):

| Env var | Overrides | Notes |
| --- | --- | --- |
| `ECHODRAFT_LLM_PROVIDER` | `provider` | lower-cased |
| `ECHODRAFT_LLM_BASE_URL` | `base_url` | |
| `ECHODRAFT_LLM_MODEL` | `model` | |
| `ECHODRAFT_LLM_API_KEY` | `api_key` | |
| `ECHODRAFT_LLM_CLOUD_CONSENT` | `cloud_consent` | truthy values: `1`, `true`, `yes` |

The resolved settings carry an `env_overrides` list so the API and UI can show
which fields the environment is pinning.

**The API key is stored locally and never echoed.** `GET /api/v1/llm/settings`
returns only `hasApiKey: bool`; the dashboard key field is write-only.

## The consent gate

Cloud usage requires an explicit acknowledgment that manuscript text will be
sent to the provider's servers. The gate (`ensure_cloud_ready`) requires
consent **plus** an API key, base URL, and model, and is enforced at **two
points**:

1. **Activation** — `PUT /api/v1/llm/settings` returns 422 when switching to
   `openai_compat` without consent, without a key (payload, stored, or env),
   or without a base URL/model.
2. **Call time** — `LocalLlmService.extract` re-checks the effective settings
   before any request is sent, so an env-configured cloud provider without
   `ECHODRAFT_LLM_CLOUD_CONSENT=1` (or a key) fails before any manuscript text
   leaves the process.

The connection test deliberately sits outside the gate: it sends no manuscript
data (only `GET /models`), so it works before consent is given.

## Routing semantics

- **Global model override.** `LocalLlmService` resolves settings at
  construction. When the provider is `openai_compat`, the configured cloud
  model **replaces the per-stage defaults for every generate call** —
  structure v1 refinement and structure v2 MAP/REDUCE/repair, cast discovery,
  speaker attribution (including self-consistency vote samples), direction
  inference, atmosphere profiles, and voice labeling. One provider, one model,
  one mental model. Per-stage model defaults (`qwen3:4b` etc.) apply only when
  the provider is Ollama.
- **Embeddings always run on Ollama.** `LocalLlmService.embed` is hard-wired
  to the Ollama provider regardless of the active generate provider (xAI
  serves no embeddings endpoint; cast clustering is cheap and
  quality-insensitive). `installed_models()` likewise always reports Ollama
  tags.
- **Model availability check.** For cloud, `_require_model` verifies the
  configured model appears in the cached `/models` listing; for Ollama the
  existing installed-tags check is unchanged.
- **Honest provenance.** Every `llm_runs` row records the provider
  (`ollama` | `openai_compat`) and the model that actually ran, and the
  dashboard shows an active-provider badge — a production run is never
  ambiguous about which brain produced it.

## Failure semantics

Fail closed, resumable — a cloud failure is indistinguishable in shape from a
local one:

- Every transport/protocol problem (HTTP 4xx/5xx, timeout, network error,
  malformed response) normalizes to `ValueError` inside the provider.
- The existing service path applies unchanged: the `llm_runs` row records the
  error, the checkpoint unit is marked failed, the job reports it, and resume
  re-runs only failed units while the inference cache preserves completed
  work.
- There are **no provider-level retries** beyond the one sticky
  structured-output fallback, and **no silent fallback to the local model** —
  output provenance stays single-sourced per run. Rate-limit backoff is
  deliberately out of scope (fail closed is the contract).

## Inference-cache namespacing

The inference cache key gains a `"provider"` field **only when the provider is
not Ollama**. Local keys keep their historical payload shape, so:

- all existing local cache entries and checkpoint `output_ref`s keep their
  identity (no invalidation on upgrade), and
- a cloud draw can never collide with a local draw for the same
  prompt/schema/model string.

## API surface

### `GET /api/v1/llm/settings`

Returns the effective (DB + env) settings. The key is never included.

```json
{
  "provider": "openai_compat",
  "baseUrl": "https://api.x.ai/v1",
  "model": "grok-4.5",
  "cloudConsent": true,
  "hasApiKey": true,
  "envOverrides": ["model"]
}
```

### `PUT /api/v1/llm/settings`

Updates the stored row atomically under the writer lock (read-modify-write is
recomputed inside the writer callable, so concurrent PUTs cannot revert a key
change). Key semantics: `apiKey` **omitted/null = keep** the stored key,
`""` = **clear** it, any other string replaces it.

```json
{
  "provider": "openai_compat",
  "baseUrl": "https://api.x.ai/v1",
  "model": "grok-4.5",
  "apiKey": "xai-...",
  "cloudConsent": true
}
```

Responds with the same shape as `GET`. Returns **422** for: an unknown
provider, cloud activation without `cloudConsent: true`, cloud activation
without any API key (payload, stored, or env), or a missing base URL/model.

### `POST /api/v1/llm/settings/test`

Connection test against the **submitted** (not yet saved) settings — calls
`GET {baseUrl}/models` (cache bypassed), sends no manuscript data, works
pre-consent, and never raises: failures come back in the body.

```json
{ "baseUrl": "https://api.x.ai/v1", "apiKey": "xai-...", "model": "grok-4.5" }
```

`apiKey` omitted/null means "use the stored/env key". Response:

```json
{
  "ok": true,
  "models": ["grok-4.5", "grok-4.5-mini"],
  "modelFound": true,
  "error": null
}
```

On failure `ok` is `false`, `models` is empty, `modelFound` is `null`, and
`error` carries the provider message.

## Dashboard

The **AI Provider** card (`apps/web/app/components/setup/AiProviderCard.tsx`,
mounted next to Model Center) exposes the provider toggle, xAI-prefilled
base-URL/model fields, the write-only key field (with "key saved" state), the
consent checkbox that gates Save for cloud, the test-connection button
(surfacing the returned model list / model-found check / error), the
active-provider badge (e.g. `cloud · grok-4.5`), and a notice when env vars
override stored fields.

## Out of scope (deliberate)

Chunk-size tuning for large-context cloud models (V3 follow-up), per-stage
provider routing, multiple named provider profiles, Anthropic-native adapters,
OS-keyring key storage, cost/token accounting, and retry-with-backoff on rate
limits.
