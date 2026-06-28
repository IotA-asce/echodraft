import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from echodraft_domain import (
    EmbeddingRequest,
    EmbeddingResult,
    LlmExtractionRequest,
    LlmExtractionResult,
)

from .container import AppContainer
from .ollama_models import find_ollama_model

DEFAULT_EXTRACTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "confidence"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["characters", "warnings"],
}


@dataclass(frozen=True)
class OllamaGenerateResult:
    response: dict[str, object]
    raw: dict[str, object]


class SchemaValidationError(ValueError):
    pass


class OllamaProvider:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def tags(self) -> list[dict[str, object]]:
        payload = self._post_or_get("GET", "/api/tags")
        models = payload.get("models")
        if not isinstance(models, list):
            raise ValueError("Ollama returned an unexpected /api/tags response.")
        return [cast(dict[str, object], item) for item in models if isinstance(item, dict)]

    def generate_json(
        self, model: str, prompt: str, schema: dict[str, object]
    ) -> OllamaGenerateResult:
        payload = self._post_or_get(
            "POST",
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": schema,
            },
            timeout=180,
        )
        raw_response = payload.get("response")
        if not isinstance(raw_response, str):
            raise ValueError("Ollama generate response did not include text response.")
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as error:
            raise ValueError("Ollama response was not valid JSON.") from error
        if not isinstance(parsed, dict):
            raise ValueError("Ollama response JSON must be an object.")
        return OllamaGenerateResult(response=cast(dict[str, object], parsed), raw=payload)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        payload = self._post_or_get(
            "POST",
            "/api/embed",
            {"model": request.model, "input": request.input},
            timeout=120,
        )
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise ValueError("Ollama embed response did not include embeddings.")
        return EmbeddingResult(
            model=str(payload.get("model") or request.model),
            embeddings=[
                [float(value) for value in vector]
                for vector in embeddings
                if isinstance(vector, list)
            ],
        )

    def _post_or_get(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        timeout: int = 10,
    ) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ValueError(f"Ollama request failed for {path}: {error}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"Ollama returned non-object JSON for {path}.")
        return cast(dict[str, object], parsed)


class LocalLlmService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.provider = OllamaProvider(container.settings.ollama_base_url)

    def installed_models(self) -> list[dict[str, object]]:
        return self.provider.tags()

    def extract(
        self, project_id: str, request: LlmExtractionRequest, job_id: str | None = None
    ) -> LlmExtractionResult:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        source = (
            self.container.sources.get(request.source_document_id)
            if request.source_document_id
            else self.container.sources.latest(project_id)
        )
        if not source or not source.canonical_path:
            raise ValueError("A successfully imported canonical source is required.")
        self._require_model(request.model)
        schema = request.output_schema or DEFAULT_EXTRACTION_SCHEMA
        text = Path(source.canonical_path).read_text(encoding="utf-8")[:12000]
        prompt = request.prompt or self._prompt(request.task, text)
        run_id = f"llmrun_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "llm" / run_id
        root.mkdir(parents=True, exist_ok=True)
        prompt_path = root / "prompt.md"
        response_path = root / "response.json"
        prompt_path.write_text(prompt, encoding="utf-8")
        run = self.container.llm_runs.create(
            run_id,
            project_id=project_id,
            source_document_id=source.id,
            provider="ollama",
            model=request.model,
            task=request.task,
            prompt_path=str(prompt_path),
            schema=schema,
        )
        retries = 0
        errors: list[str] = []
        try:
            for attempt in range(2):
                candidate_prompt = prompt
                if errors:
                    candidate_prompt = (
                        f"{prompt}\n\nPrevious response failed validation: {'; '.join(errors)}. "
                        "Return only JSON that satisfies the schema."
                    )
                result = self.provider.generate_json(request.model, candidate_prompt, schema)
                errors = validate_json_schema(result.response, schema)
                retries = attempt
                if not errors:
                    response_path.write_text(json.dumps(result.raw, indent=2), encoding="utf-8")
                    run = self.container.llm_runs.complete(
                        run_id,
                        status="succeeded",
                        response_path=str(response_path),
                        result=result.response,
                        retries=retries,
                    )
                    if job_id:
                        self.container.jobs_repository.set_progress(
                            job_id, {"phase": "llm_extract", "runId": run_id, "status": "succeeded"}
                        )
                    return LlmExtractionResult(run=run, result=result.response)
            raise SchemaValidationError("; ".join(errors) or "Response failed schema validation.")
        except Exception as error:
            run = self.container.llm_runs.complete(
                run_id,
                status="failed",
                response_path=str(response_path) if response_path.exists() else None,
                error_message=str(error),
                retries=retries,
            )
            if job_id:
                self.container.jobs_repository.set_progress(
                    job_id, {"phase": "llm_extract", "runId": run_id, "status": "failed"}
                )
            raise ValueError(f"Local LLM extraction failed closed: {run.error_message}") from error

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self._require_model(request.model)
        return self.provider.embed(request)

    def _require_model(self, model: str) -> None:
        models = self.provider.tags()
        if not find_ollama_model(models, model):
            raise ValueError(f"Ollama model {model} is not installed. Pull it in Model Center first.")

    @staticmethod
    def _prompt(task: str, text: str) -> str:
        return (
            "You are extracting audiobook production metadata from a manuscript. "
            "Return only JSON that satisfies the supplied schema. "
            f"Task: {task}.\n\nManuscript excerpt:\n{text}"
        )


def validate_json_schema(value: object, schema: dict[str, object], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path} must be an object"]
        properties = schema.get("properties")
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key} is required")
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(
                        validate_json_schema(
                            value[key], cast(dict[str, object], child_schema), f"{path}.{key}"
                        )
                    )
    elif expected == "array":
        if not isinstance(value, list):
            return [f"{path} must be an array"]
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, cast(dict[str, object], items), f"{path}[{index}]"))
    elif expected == "string" and not isinstance(value, str):
        errors.append(f"{path} must be a string")
    elif expected == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
        errors.append(f"{path} must be an integer")
    elif expected == "number" and not (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    ):
        errors.append(f"{path} must be a number")
    elif expected == "boolean" and not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")
    return errors
