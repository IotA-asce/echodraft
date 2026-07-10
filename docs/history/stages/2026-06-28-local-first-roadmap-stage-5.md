# Local-First Roadmap Stage 5 Implementation Plan

Goal: implement the first local LLM service backed by Ollama.

## Scope

- Add `llm_runs` records for prompt, schema, response, result, status, retry, and error metadata.
- Add an Ollama provider that uses `/api/tags`, `/api/generate`, and `/api/embed`.
- Keep model acquisition explicit through Model Center `ollama pull`.
- Add schema-first extraction jobs with JSON Schema passed to Ollama `format`.
- Validate JSON responses locally and fail closed after one retry.
- Add local embedding API support.
- Document Local LLM operation and artifacts.

## Implementation Notes

- Default base URL is `http://127.0.0.1:11434`, overridable with `ECHODRAFT_OLLAMA_BASE_URL`.
- Extraction jobs write prompt and raw response artifacts under the project artifact store.
- Tests fake the Ollama provider so committed validation does not require local models.
- There is no cloud fallback.

## Validation

Run:

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/db/src libs/domain-models/src
npm run web:typecheck
npm run web:lint
```

Expected result: all checks pass.
