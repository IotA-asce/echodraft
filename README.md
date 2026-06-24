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

## Development Status

The staged MVP implementation (foundations through alpha hardening) is present on `main`. The current development baseline includes ingestion, structure extraction, casting and direction records, segment rendering, chapter assembly, review and selective patching, WAV/MP3 export packaging, and interrupted-job reconciliation.

The project is an alpha rather than a finished studio application. The main remaining product work is real ambience asset mixing, dashboard controls for advanced production actions, M4B packaging, and external alpha validation. See [implement/README.md](implement/README.md) for the stage map and [plans/phase-roadmap.md](plans/phase-roadmap.md) for the broader roadmap.

## Developer Setup

### Prerequisites

- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/).
- Node.js 20 or later and npm.
- `ffmpeg` with MP3 encoding support for MP3 exports.

The API and dashboard can be developed on Windows, macOS, and Linux. The commands below use PowerShell on Windows; run them from the repository root.

### Windows Prerequisites

On Windows 10 or 11, install Git, Python, Node.js, `uv`, and `ffmpeg`. One convenient option is Windows Package Manager:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell after installation, then confirm the tools are on `PATH`:

```powershell
git --version
python --version
node --version
npm --version
uv --version
ffmpeg -version
```

If the `python` command opens the Microsoft Store instead, disable the Python app execution aliases in Windows Settings or use the Python launcher (`py -3.12`) to confirm the installation. If `ffmpeg` is not found, reopen the terminal before changing `PATH` manually.

### Windows Install

```powershell
git clone <repository-url>
Set-Location echodraft

uv sync --group dev
npm install
Copy-Item .env.example .env
```

The checked-in defaults keep SQLite data and generated artifacts under `.echodraft` in the repository. Windows Defender or another antivirus scanner may slow large local audio-artifact directories; exclude `.echodraft` only if you understand and accept the local security trade-off.

### Windows Run

Start the API in one PowerShell window:

```powershell
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

Start the dashboard in a second PowerShell window:

```powershell
npm run web:dev
```

Open `http://localhost:3000`. The API is available at `http://localhost:8000`; `Invoke-RestMethod http://localhost:8000/health` provides a quick liveness check.

To override an API setting for the current PowerShell session, use environment variables before starting Uvicorn:

```powershell
$env:ECHODRAFT_DATABASE_URL = "sqlite:///./.echodraft/echodraft.db"
$env:ECHODRAFT_ARTIFACT_ROOT = ".\.echodraft\projects"
$env:ECHODRAFT_TTS_PROVIDER = "mock"
```

Next.js reads `NEXT_PUBLIC_API_URL` from `.env`. The API uses the same local defaults shown in `.env.example`; API overrides must be exported in the shell as above.

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

The default `mock` provider creates deterministic silent WAV fixtures. To use real local synthesis, install a Kokoro-compatible CLI for your operating system and explicitly register locally licensed model and voice files. No model is downloaded automatically.

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

On Windows, set absolute paths with PowerShell before starting the API. Quoted values are recommended when paths contain spaces:

```powershell
$env:ECHODRAFT_TTS_PROVIDER = "kokoro"
$env:ECHODRAFT_KOKORO_EXECUTABLE = "C:\Tools\kokoro\kokoro-tts.exe"
$env:ECHODRAFT_KOKORO_MODEL_PATH = "C:\Models\kokoro\model.bin"
$env:ECHODRAFT_KOKORO_VOICE_PATH = "C:\Models\kokoro\voices.txt"
```

If the executable, model, registry, or requested voice is unavailable, preview and rendering fail with recovery guidance rather than falling back silently. Keep `ECHODRAFT_TTS_PROVIDER=mock` for CI and workflow development without local model files. The configured Kokoro executable must be available on `PATH` or set to an absolute executable path.

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

The same commands work in PowerShell. The browser smoke test is optional for documentation-only changes and requires Playwright's Chromium binary:

```powershell
npx playwright install chromium
npm run web:test:smoke
```

Run database migrations against a local SQLite database when persistence changes:

```bash
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db \
  uv run alembic -c libs/db/alembic.ini upgrade head
```

PowerShell equivalent:

```powershell
$env:ECHODRAFT_DATABASE_URL = "sqlite:///./.tmp/echodraft-migration.db"
uv run alembic -c libs/db/alembic.ini upgrade head
Remove-Item Env:ECHODRAFT_DATABASE_URL
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
