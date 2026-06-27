# Model Center

Document date: 2026-06-28

Model Center is the first local AI subsystem surface. It gives the dashboard and API one place to inspect, install, verify, and track local tools and models before roadmap stages depend on them.

## Catalog

The versioned catalog lives at `apps/api/src/echodraft_api/local_ai/model_catalog.yaml`.

Stage 1 includes:

- Poppler PDF tools for page rendering;
- Tesseract for baseline OCR;
- FFmpeg for audio conversion and future mixing;
- Ollama as the first local LLM runtime;
- Qwen3 Ollama model entries for local LLM and embeddings;
- managed Kokoro 82M ONNX as the default local TTS entry.

Each catalog entry declares capability, provider, install type, package-manager identifiers where applicable, size estimate, license summary, and whether it is required.

## Installation

Install jobs use the existing Echodraft job runner and persist extra install metadata in `model_install_jobs`.

Supported install types in Stage 1:

- `system_tool`: installs with Homebrew on macOS, winget on Windows, and apt-get on Debian/Ubuntu-style Linux systems;
- `ollama_model`: runs `ollama pull` after the Ollama runtime is available;
- `kokoro_managed`: delegates to the existing managed Kokoro ONNX setup service.

Install requests require explicit confirmation for network downloads, third-party license review, and system package installation where relevant. Unsupported operating systems or package managers fail with actionable errors instead of silently falling back.

## Health And Persistence

Health checks are runtime checks, while installation records are persisted verification snapshots.

- System tools are checked with `PATH` lookup and version commands.
- Ollama models are checked through the local Ollama tags API at `http://127.0.0.1:11434/api/tags`.
- Kokoro health reuses the managed Kokoro setup status.

Installation records live in `model_installations` and store model key, capability, provider, version/path, status, verification time, size estimate, license summary, and any error message.

## API

The implemented API surface is:

- `GET /api/v1/local-ai/catalog`
- `GET /api/v1/local-ai/installed`
- `POST /api/v1/local-ai/models/{model_key}/install`
- `POST /api/v1/local-ai/models/{model_key}/verify`
- `DELETE /api/v1/local-ai/models/{model_key}`
- `GET /api/v1/local-ai/models/{model_key}/health`
- `GET /api/v1/local-ai/jobs/{job_id}`

System package uninstall is intentionally not supported by Echodraft. App-managed entries can be removed by their provider-specific uninstall path.
