# echodraft

Local-first AI audiobook production, starting with a durable project desk: SQLite metadata, local artifact folders, and a project creation UI.

## Foundation commands

```bash
uv sync --group dev
npm install
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
npm run web:lint
npm run web:typecheck
```

Run the API with `uv run --package echodraft-api uvicorn echodraft_api.main:app --reload` and the dashboard with `npm run web:dev`.

Copy `.env.example` to `.env` to override the local SQLite database and artifact root. No cloud service is required.
