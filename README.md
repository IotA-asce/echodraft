# echodraft

`echodraft` is a local-first AI audiobook production system. It turns a manuscript into a reviewable sequence of chapters, scenes, segments, voice renders, chapter stems, and export artifacts without sending manuscript or audio data to a cloud service by default.

The MVP is deliberately segment-first and manifest-driven: a segment is the smallest editable and renderable unit, render history is append-only, and a correction rerenders only the affected segment and chapter.

## What Is Implemented

- Local project workspace backed by SQLite metadata and filesystem artifacts.
- TXT, Markdown, DOCX, and EPUB manuscript ingestion with preserved originals and canonical text.
- Chapter, scene, and sentence-safe segment extraction.
- Character, voice, pronunciation, direction, and mock local TTS preview records.
- Immutable segment renders and chapter speech assembly with manifests, waveform metadata, and validation reports.
- Review issues, comments, QA findings, selective segment patching, and chapter reassembly.
- Local WAV and MP3 export packages with checksums and export manifests.
- Startup reconciliation for interrupted in-process jobs and recovery-oriented error messages.

## Current Limits

- The default TTS backend is `mock` for tests and setup. A configured local Kokoro CLI can generate real WAV output; the repository does not bundle Kokoro models or voices.
- WAV and MP3 exports are available through the local `ffmpeg` toolchain. M4B remains deferred.
- The ambience data model and render modes exist, but source asset mixing and the related dashboard controls are not complete.
- The web dashboard currently covers project creation, manuscript intake, structure browsing, and segment editing. Advanced production actions are available through the API.

## Developer Setup

### Prerequisites

- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/).
- Node.js 20 or later and npm.
- `ffmpeg` with MP3 encoding support for MP3 exports.

The API and dashboard run on macOS and Linux. Windows is not currently a supported development or production target.

Install `ffmpeg` on macOS:

```bash
brew install ffmpeg
```

Install `ffmpeg` on Debian/Ubuntu Linux:

```bash
sudo apt update
sudo apt install ffmpeg
```

For Fedora Linux:

```bash
sudo dnf install ffmpeg
```

### Install

```bash
git clone <repository-url>
cd echodraft

uv sync --group dev
npm install
cp .env.example .env
```

The default `.env` keeps all state local:

```dotenv
ECHODRAFT_DATABASE_URL=sqlite:///./.echodraft/echodraft.db
ECHODRAFT_ARTIFACT_ROOT=./.echodraft/projects
NEXT_PUBLIC_API_URL=http://localhost:8000
ECHODRAFT_TTS_PROVIDER=mock
```

`ECHODRAFT_ARTIFACT_ROOT` stores source files, manifests, audio artifacts, exports, and logs. Audio binaries are never stored in the relational database.

### Enable Local Kokoro TTS

The default `mock` provider creates deterministic silent WAV fixtures. To use real local synthesis, install a Kokoro-compatible CLI for your macOS or Linux architecture and explicitly register locally licensed model and voice files. No model is downloaded automatically.

```dotenv
ECHODRAFT_TTS_PROVIDER=kokoro
ECHODRAFT_KOKORO_EXECUTABLE=kokoro-tts
ECHODRAFT_KOKORO_MODEL_PATH=/absolute/path/to/kokoro-model.bin
ECHODRAFT_KOKORO_VOICE_PATH=/absolute/path/to/voices.txt
```

The voice registry is a local text file containing one approved voice ID per line; retain the model and voice license/provenance outside the repository. The configured executable must support this invocation and write a non-empty WAV file:

```bash
kokoro-tts \
  --model "$ECHODRAFT_KOKORO_MODEL_PATH" \
  --voices "$ECHODRAFT_KOKORO_VOICE_PATH" \
  --voice <voice-id> \
  --text "Preview text" \
  --output /tmp/preview.wav
```

If the executable, model, registry, or requested voice is unavailable, preview and rendering fail with recovery guidance rather than falling back silently. Keep `ECHODRAFT_TTS_PROVIDER=mock` for CI and workflow development without local model files. The configured Kokoro executable must be available on `PATH` or be set to an absolute Linux/macOS executable path.

### Run Locally

Start the API in one terminal:

```bash
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

Start the Next.js dashboard in another terminal:

```bash
npm run web:dev
```

Open `http://localhost:3000`. The API is available at `http://localhost:8000`; use `GET /health` for liveness and `GET /ready` for local storage readiness.

### Validate Changes

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
npm run web:lint
npm run web:typecheck
```

Run database migrations against a local SQLite database when persistence changes:

```bash
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db \
  uv run alembic -c libs/db/alembic.ini upgrade head
```

## Core Workflow

1. Create a project and declare rights.
2. Import a manuscript and inspect parser warnings.
3. Extract chapters, scenes, and segments.
4. Configure voices, pronunciation, and direction.
5. Render segments and assemble a chapter speech stem.
6. Review QA issues, patch individual segments, then reassemble only the affected chapter.
7. Export validated WAV or MP3 chapter files and retain the export manifest.

## Repository Layout

| Path | Responsibility |
| --- | --- |
| `apps/api` | FastAPI application, jobs, pipeline services, and HTTP contracts. |
| `apps/web` | Next.js local dashboard. |
| `libs/domain-models` | Shared Pydantic API/domain models. |
| `libs/db` | SQLAlchemy models, repositories, and Alembic migrations. |
| `docs` | Product, architecture, domain, API, and operating specifications. |
| `plans` | Execution plans and roadmap. |
| `implement` | Stage-by-stage implementation briefs. |

## Engineering Rules

- Keep changes modular and local-first.
- Preserve append-only segment and chapter render history.
- Never put audio blobs in SQLite or another relational database.
- Treat segments as the atomic editable and renderable unit.
- Update manifests whenever pipeline inputs or outputs change.

Read [docs/README.md](docs/README.md) for the documentation map and [AGENTS.md](AGENTS.md) for repository workflow requirements.


## Future scopes

Curation:
- Small studio beta
- publisher-grave v1

voice expreience:
- multi-voice
