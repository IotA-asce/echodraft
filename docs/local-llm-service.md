# Local LLM Service

Stage 5 adds the first local LLM runtime integration through Ollama. It uses the current Ollama API behavior documented in the official Ollama API docs:

- `GET /api/tags` lists local models;
- `ollama pull <model>` is used by Model Center for model acquisition;
- `POST /api/generate` accepts `stream: false` and a JSON Schema object in `format`;
- `POST /api/embed` returns embedding vectors.

## Runtime Contract

The service is local-only and fail-closed.

- If Ollama is unreachable, the request fails.
- If the requested model is not present in `/api/tags`, the request fails with recovery guidance to pull it through Model Center.
- If the model returns invalid JSON, the request is retried once with validation feedback.
- If the response still does not satisfy the schema, the run is marked failed.

## APIs

- `GET /api/v1/local-llm/ollama/models`
- `POST /api/v1/projects/{project_id}/local-llm/extractions`
- `GET /api/v1/projects/{project_id}/llm-runs`
- `GET /api/v1/llm-runs/{run_id}`
- `POST /api/v1/local-llm/embeddings`

Extraction requests return a normal background job. The resulting `llm_runs` row stores prompt path, response path, schema, parsed result, retry count, and error details.

## Artifacts

LLM artifacts are stored under:

```text
{project_artifact_path}/llm/{llm_run_id}/prompt.md
{project_artifact_path}/llm/{llm_run_id}/response.json
```

## Configuration

Default Ollama base URL:

```text
http://127.0.0.1:11434
```

Override with:

```bash
export ECHODRAFT_OLLAMA_BASE_URL='http://127.0.0.1:11434'
```

## Constraints

- No manuscript text is sent to cloud services.
- No silent fallback to cloud or mock LLMs is allowed.
- Committed tests use fake providers and do not require Ollama to be running.
