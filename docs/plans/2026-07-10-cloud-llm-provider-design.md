# Cloud LLM Provider Integration — Design (xAI / Grok first)

**Date:** 2026-07-10
**Status:** Approved design, pre-implementation
**Owner branch:** `feat/cloud-llm-provider`

## Purpose

Let Echodraft optionally route all LLM generate calls to a cloud provider —
first target: the xAI API with `grok-4.5` — to improve extraction quality and
speed over the local `qwen3:4b` Ollama baseline. Local-first remains the
default and the only mandatory mode; cloud usage is strictly opt-in behind an
explicit consent gate.

## Decisions (settled with the repo owner)

| Decision | Choice |
| --- | --- |
| Provider scope | Generic OpenAI-compatible adapter; xAI is the first configured instance |
| Selection mechanism | DB-persisted settings + dashboard UI (single global active provider) |
| Consent | Hard gate: cloud provider cannot activate without an explicit acknowledgment (same pattern as XTTS voice consent) |
| API key storage | Local SQLite settings row; `ECHODRAFT_LLM_*` env vars override at read time; UI never echoes the stored key |
| Failure mode | Fail closed — a cloud call failure behaves exactly like an Ollama failure (llm_runs record, checkpoint failed, resumable) |

## What routes through the cloud provider

Every stage already funnels generate calls through `LocalLlmService.extract`
(`apps/api/src/echodraft_api/local_llm.py`), so a single provider switch covers:

- Structure v1 LLM refinement and structure v2 MAP/REDUCE/repair (segmentation)
- Cast discovery (character bible: characters, aliases, traits)
- Speaker attribution, including self-consistency vote samples
- Direction inference (emotion, pace, intensity, pauses)
- Atmosphere profiles (per-scene sound-planning descriptors)
- Voice labeling (when `ECHODRAFT_VOICE_LABELING_ENABLED`)

**Embeddings always stay on Ollama** (`LocalLlmService.embed`): xAI serves no
embeddings endpoint, and cast clustering is cheap and quality-insensitive.

## Architecture

### 1. Provider adapter — `OpenAiCompatProvider`

New class in a sibling module `llm_providers.py` (keeping `local_llm.py` from
growing further; `OllamaLlmProvider` stays where it is), implementing the same
narrow surface the service consumes:

- `infer(model, prompt, schema, *, temperature=None, seed=None) -> GenerateResult`
  - `POST {base_url}/chat/completions` with a system message (the existing
    "return exactly one JSON object" instruction), the user prompt, and
    `response_format: {"type": "json_schema", "json_schema": {"name": <task>,
    "schema": <schema>, "strict": true}}`.
  - `temperature` maps directly (default 0 to match the deterministic Ollama
    default); `seed` maps to the OpenAI-compatible `seed` field.
  - **Fallback:** if the endpoint rejects `json_schema` (HTTP 400 naming
    `response_format`), retry once with `{"type": "json_object"}` and the
    schema embedded in the prompt. The fallback is per-provider-instance
    sticky (first 400 flips a flag) to avoid paying the failed request per call.
  - Response text goes through the existing `parse_llm_json_object`;
    `validate_json_schema` + the 2-attempt repair loop in
    `LocalLlmService.extract` remain the enforcement layer above the provider.
- `available_models() -> list[str]` via `GET {base_url}/models` (also used by
  the test-connection endpoint). Result is cached per service instance so
  extraction does not pay a network round trip per unit.
- `embed(request)` raises a "not supported" `ValueError`; the service never
  calls it (embeds are hard-wired to the Ollama provider).

Transport: `urllib` with `Authorization: Bearer <key>`, 180 s timeout,
matching the Ollama adapter — no new dependency. HTTP 429/5xx/timeouts/network
errors normalize to `ValueError` with the status and provider name in the
message, keeping the existing fail-closed path intact. No provider-level
retries beyond the sticky fallback; the service's validation loop and the
orchestrator's resume are the retry story.

### 2. Settings persistence

- Alembic migration **0038** adds a single-row `llm_settings` table:

  | column | type | default |
  | --- | --- | --- |
  | `id` | int PK | 1 (enforced single row) |
  | `provider` | text | `"ollama"` (`"ollama"` \| `"openai_compat"`) |
  | `base_url` | text nullable | null (UI pre-fills `https://api.x.ai/v1`) |
  | `model` | text nullable | null (UI pre-fills `grok-4.5`, free text) |
  | `api_key` | text nullable | null |
  | `cloud_consent` | bool | false |
  | `updated_at` | datetime | — |

- `LlmSettingsRepository` in `libs/db` with `get()` / `update(...)`, writes via
  the existing writer pool.
- **Env overrides** (read-time, for CI/headless): `ECHODRAFT_LLM_PROVIDER`,
  `ECHODRAFT_LLM_BASE_URL`, `ECHODRAFT_LLM_MODEL`, `ECHODRAFT_LLM_API_KEY`.
  Env consent shortcut: activating a cloud provider purely via env requires
  `ECHODRAFT_LLM_CLOUD_CONSENT=1` — the gate applies in every path.

### 3. Service integration and routing

- `LocalLlmService` resolves effective settings (DB row merged with env
  overrides) and constructs the generate provider accordingly; it always keeps
  an Ollama provider instance for `embed`.
- When the active provider is cloud, the configured cloud model **replaces**
  the per-stage `qwen3:4b` defaults for every generate call (global routing —
  one mental model). `llm_runs.provider` / `.model` record what actually ran.
- `_require_model`: unchanged for Ollama; for cloud, verifies the configured
  model appears in the cached `available_models()` result.
- **Inference cache key:** gains a `"provider"` field **only when the provider
  is not Ollama**, so all existing local cache entries and checkpoint
  `output_ref`s keep their identity, and a Grok draw can never collide with a
  local draw. (Same pattern as the temperature/seed key extension.)
- Consent re-check at call time: if the effective provider is cloud and
  consent or key is missing, `extract` raises before any request is sent.

### 4. API surface (FastAPI, `main.py` + `libs/domain-models`)

- `GET /llm/settings` — current effective settings. The key is never echoed:
  the response carries `hasApiKey: bool` plus which fields are env-overridden.
- `PUT /llm/settings` — update provider/base_url/model/api_key/consent.
  Rejects (422) activating `openai_compat` unless consent is true and a key is
  present (in the payload, the DB, or the env). An omitted `api_key` field
  leaves the stored key untouched; an explicit empty string clears it.
- `POST /llm/settings/test` — connection test against the *submitted* (not yet
  saved) settings: calls `GET /models`, returns `{ok, models[] | error}`.
  Sends no manuscript data, so it works pre-consent.

### 5. Dashboard UI (`apps/web`)

An "AI Provider" card in the Model Center area:

- Provider toggle: **Local (Ollama)** / **Cloud (OpenAI-compatible)**.
- Cloud fields: base URL (pre-filled `https://api.x.ai/v1`), model (pre-filled
  `grok-4.5`), API key (masked, write-only; shows "key saved" state).
- Consent checkbox with explicit copy: *"I understand manuscript text will be
  sent to this provider's servers. Echodraft remains local-first; this is
  strictly opt-in."* Save is disabled for cloud until ticked.
- **Test connection** button surfacing the returned model list (confirms the
  configured model exists) or the error.
- Active-provider badge (e.g. `cloud · grok-4.5`) so production runs are never
  ambiguous about what produced them.
- Monochrome tokens, TanStack Query mutation + invalidation; no new routes.

### 6. Docs and messaging

- README privacy copy: "local-first by default — optional bring-your-own-key
  cloud LLM providers, strictly opt-in behind a consent gate; nothing leaves
  your machine unless you turn that on." Table row and Rights section stay
  accurate.
- New `docs/architecture/local-ai/cloud-llm-providers.md` (provider contract,
  settings, consent, failure semantics) linked from `docs/README.md`.
- `docs/progress-tracker.md` entry on completion.

## Failure semantics (summary)

A cloud unit failure is indistinguishable in shape from a local one: recorded
in `llm_runs` with the error, checkpoint marked failed, job reports it, resume
re-runs only failed units, inference cache preserves completed work. No silent
fallback to the local model — output provenance stays single-sourced per run.

## Out of scope (deliberate)

- **Chunk-size tuning for large-context models.** The pipeline still chunks
  for a 4B local model; Grok's context window would allow far bigger chunks
  and fewer calls. That is a follow-up tuning task (V3), after this lands.
- Per-stage provider routing, multiple named provider profiles, Anthropic/
  native-API adapters, OS-keyring storage, cost/token accounting.

## Testing

- **Provider unit tests** (stubbed HTTP): chat/completions payload shape
  (json_schema response_format, temperature/seed), sticky json_object
  fallback, 429/5xx/timeout → `ValueError`, `available_models` parsing,
  `embed` unsupported.
- **Service tests:** cloud model override of per-stage defaults, consent gate
  (DB and env paths), env-over-DB precedence, cache-key provider separation
  (existing Ollama keys unchanged), fail-closed on provider error, embeddings
  still routed to Ollama.
- **API tests:** settings round-trip with key masking, key-preserving partial
  update, 422 on consent-less cloud activation, test-connection endpoint.
- **Migration:** disposable-DB `alembic upgrade head`.
- **Full standard gate:** `uv run pytest`, `ruff`, `mypy`, `npm run web:lint`,
  `web:typecheck`, `web:test:smoke`.

## Verification of intent

Done means: with no configuration, Echodraft behaves byte-for-byte as today
(pure local). With the xAI key entered, consent ticked, and the provider
switched, a full extraction run (structure → cast → attribution → direction →
atmosphere) executes every generate call against `grok-4.5`, records honest
provenance, survives mid-run failures resumably, and the dashboard always
shows which brain produced the book.
