import hashlib
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
from .llm_providers import (
    EffectiveLlmSettings,
    GenerateResult,
    OpenAiCompatProvider,
    ensure_cloud_ready,
    parse_llm_json_object,
    resolve_effective_llm_settings,
)
from .ollama_models import find_ollama_model
from .orchestrator import CheckpointStore, Stage, Unit

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
class CheckpointContext:
    """Content-addressed orchestrator checkpoint for a single LLM extraction unit.

    Passing this into :meth:`LocalLlmService.extract` records the unit's progress in
    the orchestrator checkpoint store so that a resumed job can observe which units
    already completed. The inference cache makes the actual recomputation cheap; the
    checkpoint makes the skip deterministic and observable.
    """

    job_id: str
    project_id: str | None
    stage: str
    scope: dict[str, object]
    stage_version: str = "1"

    def unit(self) -> Unit:
        return Unit(
            stage=Stage(self.stage, self.stage_version),
            job_id=self.job_id,
            project_id=self.project_id,
            scope=self.scope,
        )


class SchemaValidationError(ValueError):
    pass


class OllamaLlmProvider:
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
        return self.infer(model, prompt, schema)

    def infer(
        self,
        model: str,
        prompt: str,
        schema: dict[str, object],
        *,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> OllamaGenerateResult:
        options: dict[str, object] = {
            # None keeps the historical deterministic default draw (temperature 0).
            "temperature": 0 if temperature is None else temperature,
            "top_p": 0.9,
            "num_predict": 4096,
        }
        if seed is not None:
            options["seed"] = seed
        payload = self._post_or_get(
            "POST",
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "system": (
                    "Return exactly one JSON object that satisfies the supplied JSON schema. "
                    "Do not include markdown, commentary, or reasoning text."
                ),
                "stream": False,
                "format": schema,
                "think": False,
                "options": options,
            },
            timeout=180,
        )
        raw_response = payload.get("response")
        if not isinstance(raw_response, str):
            raise ValueError("Ollama generate response did not include text response.")
        parsed = parse_llm_json_object(raw_response)
        return OllamaGenerateResult(response=parsed, raw=payload)

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


OllamaProvider = OllamaLlmProvider


class LocalLlmService:
    def __init__(self, container: AppContainer) -> None:
        self.container = container
        self.ollama = OllamaProvider(container.settings.ollama_base_url)
        self.effective: EffectiveLlmSettings = resolve_effective_llm_settings(container.llm_settings)
        if self.effective.provider != "ollama":
            self.provider_name = "openai_compat"
            self.provider: OllamaLlmProvider | OpenAiCompatProvider = OpenAiCompatProvider(
                self.effective.base_url or "", self.effective.api_key or ""
            )
        else:
            self.provider_name = "ollama"
            self.provider = self.ollama

    def installed_models(self) -> list[dict[str, object]]:
        return self.ollama.tags()

    def extract(
        self,
        project_id: str,
        request: LlmExtractionRequest,
        job_id: str | None = None,
        *,
        checkpoint: CheckpointContext | None = None,
    ) -> LlmExtractionResult:
        project = self.container.projects.get(project_id)
        if not project:
            raise ValueError("Project not found.")
        effective_model = request.model
        if self.provider_name != "ollama":
            ensure_cloud_ready(self.effective)
            effective_model = self.effective.model or request.model
        store: CheckpointStore | None = None
        unit: Unit | None = None
        if checkpoint is not None:
            store = CheckpointStore(self.container.orchestrator_repository)
            unit = checkpoint.unit()
        source = (
            self.container.sources.get(request.source_document_id)
            if request.source_document_id
            else self.container.sources.latest(project_id)
        )
        if not source or not source.canonical_path:
            raise ValueError("A successfully imported canonical source is required.")
        self._require_model(effective_model)
        schema = request.output_schema or DEFAULT_EXTRACTION_SCHEMA
        text = Path(source.canonical_path).read_text(encoding="utf-8")[:12000]
        prompt = request.prompt or self._prompt(request.task, text)
        run_id = f"llmrun_{uuid4().hex[:16]}"
        root = Path(project.artifact_path) / "llm" / run_id
        root.mkdir(parents=True, exist_ok=True)
        prompt_path = root / "prompt.md"
        response_path = root / "response.json"
        prompt_path.write_text(prompt, encoding="utf-8")
        run = self.container.orchestrator_pools.writer.run(
            lambda: self.container.llm_runs.create(
                run_id,
                project_id=project_id,
                source_document_id=source.id,
                provider=self.provider_name,
                model=effective_model,
                task=request.task,
                prompt_path=str(prompt_path),
                schema=schema,
            )
        )
        cache_key = _inference_cache_key(
            effective_model,
            request.task,
            prompt,
            schema,
            request.temperature,
            request.seed,
            provider=self.provider_name,
        )

        def _mark_checkpoint(status: str, *, error: str | None = None) -> None:
            if store is None or unit is None:
                return
            checkpoint_store = store
            checkpoint_unit = unit
            self.container.orchestrator_pools.writer.run(
                lambda: (
                    checkpoint_store.mark_done(checkpoint_unit, output_ref=cache_key)
                    if status == "done"
                    else checkpoint_store.mark_failed(checkpoint_unit, error or "")
                    if status == "failed"
                    else checkpoint_store.mark_running(checkpoint_unit)
                )
            )

        cached = self.container.orchestrator_pools.writer.run(
            lambda: self.container.orchestrator_repository.cache_entry(
                cache_key,
                record_hit=True,
            )
        )
        if cached and cached.value_json:
            try:
                cached_result = cast(dict[str, object], json.loads(cached.value_json))
            except json.JSONDecodeError as error:
                raise ValueError("Local LLM inference cache entry was invalid JSON.") from error
            cache_errors = validate_json_schema(cached_result, schema)
            if cache_errors:
                raise ValueError(
                    "Local LLM inference cache entry failed schema validation: "
                    + "; ".join(cache_errors)
                )
            response_path.write_text(
                json.dumps(
                    {"cached": True, "cacheKey": cache_key, "result": cached_result},
                    indent=2,
                ),
                encoding="utf-8",
            )
            run = self.container.orchestrator_pools.writer.run(
                lambda: self.container.llm_runs.complete(
                    run_id,
                    status="succeeded",
                    response_path=str(response_path),
                    result=cached_result,
                    retries=0,
                )
            )
            if job_id:
                self.container.orchestrator_pools.writer.run(
                    lambda: self.container.jobs_repository.set_progress(
                        job_id, {"phase": "llm_extract", "runId": run_id, "status": "succeeded"}
                    )
                )
            # Cache hit: the unit already produced a validated result on an earlier run, so
            # record the checkpoint as done and skip the model call entirely.
            _mark_checkpoint("done")
            return LlmExtractionResult(run=run, result=cached_result)
        retries = 0
        errors: list[str] = []
        _mark_checkpoint("running")
        try:
            for attempt in range(2):
                candidate_prompt = prompt
                if errors:
                    candidate_prompt = (
                        f"{prompt}\n\nPrevious response failed validation: {'; '.join(errors)}. "
                        "Return only JSON that satisfies the schema."
                    )
                result = self.container.orchestrator_pools.llm.run(
                    lambda: self.provider.infer(
                        effective_model,
                        candidate_prompt,
                        schema,
                        temperature=request.temperature,
                        seed=request.seed,
                    )
                )
                errors = validate_json_schema(result.response, schema)
                retries = attempt
                if not errors:
                    response_path.write_text(json.dumps(result.raw, indent=2), encoding="utf-8")
                    self.container.orchestrator_pools.writer.run(
                        lambda: self.container.orchestrator_repository.put_cache(
                            cache_key=cache_key,
                            kind="llm.generate",
                            model_id=effective_model,
                            schema_id=request.task,
                            value_json=result.response,
                            size_bytes=len(json.dumps(result.raw)),
                        )
                    )
                    run = self.container.orchestrator_pools.writer.run(
                        lambda: self.container.llm_runs.complete(
                            run_id,
                            status="succeeded",
                            response_path=str(response_path),
                            result=result.response,
                            retries=retries,
                        )
                    )
                    if job_id:
                        self.container.orchestrator_pools.writer.run(
                            lambda: self.container.jobs_repository.set_progress(
                                job_id,
                                {"phase": "llm_extract", "runId": run_id, "status": "succeeded"},
                            )
                        )
                    _mark_checkpoint("done")
                    return LlmExtractionResult(run=run, result=result.response)
            raise SchemaValidationError("; ".join(errors) or "Response failed schema validation.")
        except Exception as error:
            error_message = str(error)
            _mark_checkpoint("failed", error=error_message)
            run = self.container.orchestrator_pools.writer.run(
                lambda: self.container.llm_runs.complete(
                    run_id,
                    status="failed",
                    response_path=str(response_path) if response_path.exists() else None,
                    error_message=error_message,
                    retries=retries,
                )
            )
            if job_id:
                self.container.orchestrator_pools.writer.run(
                    lambda: self.container.jobs_repository.set_progress(
                        job_id, {"phase": "llm_extract", "runId": run_id, "status": "failed"}
                    )
                )
            raise ValueError(f"Local LLM extraction failed closed: {run.error_message}") from error

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self._require_ollama_model(request.model)
        return self.ollama.embed(request)

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
        # Sampling controls MUST be part of the key so self-consistency vote resamples
        # (temperature > 0, distinct seeds) do not collapse onto one cached draw.
        # Deterministic temperature-0 default calls always pass None here and keep their
        # historical cache identity.
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
