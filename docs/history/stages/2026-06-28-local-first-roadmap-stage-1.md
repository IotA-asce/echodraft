# Local-First Roadmap Stage 1 Implementation Plan

Goal: make local model and tool setup visible, installable, verifiable, and queryable through one Model Center surface.

## Scope

- Add a versioned local AI catalog.
- Persist installation and install-job metadata.
- Add local AI health, install, verify, uninstall, and job APIs.
- Add a dashboard Model Center section.
- Wire managed Kokoro and Ollama into the same capability registry.

## Implementation Notes

- System tool installs use Homebrew, winget, or apt-get depending on platform.
- Ollama model entries use local `ollama pull` and health-check through the local tags API.
- Kokoro installation delegates to the existing managed setup service.
- Confirmations are required before network, third-party license, or system package installation.
- Model files and logs are rooted under `.echodraft/local-ai`; existing Kokoro runtime files remain under the configured Kokoro runtime root.

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
