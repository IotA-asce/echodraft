from __future__ import annotations

from collections.abc import Iterable, Mapping


def normalize_ollama_model_name(model: object) -> str | None:
    if not isinstance(model, str):
        return None
    name = model.strip()
    if not name:
        return None
    return name if ":" in name else f"{name}:latest"


def find_ollama_model(
    models: Iterable[Mapping[str, object]], requested_model: str
) -> Mapping[str, object] | None:
    requested = normalize_ollama_model_name(requested_model)
    if requested is None:
        return None
    for model in models:
        names = (model.get("name"), model.get("model"))
        if any(normalize_ollama_model_name(name) == requested for name in names):
            return model
    return None
