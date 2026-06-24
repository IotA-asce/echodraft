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

## How to Use Echodraft

Echodraft currently has two working surfaces:

- The dashboard at `http://localhost:3000` covers project creation, manuscript import, structure extraction, browsing, and segment text editing.
- The interactive API at `http://localhost:8000/docs` covers the complete production pipeline, including casting, voice direction, rendering, chapter assembly, review patches, and export.

Keep the API running whenever you use either surface. All project metadata, source files, manifests, generated audio, and exports remain on the local machine unless you deliberately copy them elsewhere.

### 1. Check the Local Runtime

Open these endpoints before starting a project:

- `GET http://localhost:8000/health` confirms that the API process is alive.
- `GET http://localhost:8000/ready` confirms the artifact storage path is available.
- `http://localhost:8000/docs` opens FastAPI's interactive Swagger interface, where requests can be tried without a separate API client.

On PowerShell, the readiness check is:

```powershell
Invoke-RestMethod http://localhost:8000/ready
```

### 2. Create a Rights-Declared Project

In the dashboard, enter a title and optional author, confirm that you have the rights to produce the audiobook draft, and select **Create project**. Echodraft rejects projects and imports without an explicit rights declaration.

The API equivalent is `POST /api/v1/projects`:

```json
{
  "title": "My Local Audiobook",
  "author": "A. Writer",
  "description": "Private working draft",
  "rightsStatus": "declared"
}
```

Save the returned project `id`. API paths below use placeholders such as `{project_id}`, `{chapter_id}`, and `{segment_id}`; replace each placeholder with an ID returned by an earlier request.

### 3. Import a Manuscript

Open the project in the dashboard and choose a manuscript. Supported source formats are:

- plain text (`.txt`)
- Markdown (`.md` or `.markdown`)
- Word (`.docx`)
- EPUB (`.epub`)

PDF is not a supported ingestion format. Convert a PDF to one of the supported text formats first, then review the converted text before importing it. The dashboard currently limits uploads to 10 MB.

The original manuscript is preserved, while a normalized canonical text file and an import manifest are created alongside it. Review the source preview and every parser warning before continuing. **Reparse** repeats normalization from the preserved original when parser behavior changes.

For API use, call `POST /api/v1/projects/{project_id}/source/import` as multipart form data with:

- `file`: the manuscript file
- `rightsAcknowledged`: `true`
- `parserVersion`: optional; defaults to the current ingestion parser

Import and reparse operations return a job. Poll `GET /api/v1/jobs/{job_id}` until `status` is `succeeded`, `failed`, or `cancelled`. If a job fails, inspect `errorMessage` before retrying.

### 4. Extract and Review Structure

Select **Extract structure** in the dashboard after a successful import. The default maximum segment size is 600 characters. The API request is `POST /api/v1/projects/{project_id}/structure/extract`:

```json
{
  "maxSegmentChars": 600
}
```

This is also a background job. Once it succeeds, work down the hierarchy:

1. `GET /api/v1/projects/{project_id}/chapters`
2. `GET /api/v1/chapters/{chapter_id}/scenes`
3. `GET /api/v1/scenes/{scene_id}/segments`

Clicking a segment in the dashboard opens a text editor. Saving an edit creates a new segment revision rather than deleting the old text. Revision history is available from `GET /api/v1/segments/{segment_id}/revisions`.

Structure extraction uses Markdown headings as chapter signals, so clean chapter headings such as `## Chapter 1` produce the best results.

### 5. Configure Characters, Voices, and Pronunciation

These actions currently use the interactive API:

| Action | Endpoint |
| --- | --- |
| List or create characters | `GET/POST /api/v1/projects/{project_id}/characters` |
| List or create voice profiles | `GET/POST /api/v1/projects/{project_id}/voices` |
| Assign a voice to a character | `POST /api/v1/characters/{character_id}/assign-voice` |
| List or add pronunciations | `GET/POST /api/v1/projects/{project_id}/pronunciations` |
| Generate a short voice preview | `POST /api/v1/projects/{project_id}/voices/preview` |

For setup and tests, create a voice profile with `"backend": "mock"`. It produces deterministic silent WAV files and exercises the complete pipeline without a model. Use `"backend": "kokoro"` only after configuring the local Kokoro adapter described above.

Direction is explicit and reusable. A conservative narration profile looks like:

```json
{
  "scopeType": "segment",
  "scopeId": "{segment_id}",
  "pace": 1.0,
  "intensity": 0.4,
  "tone": "neutral",
  "stylePrompt": "Clear, restrained audiobook narration",
  "emphasis": false,
  "whisper": false,
  "noSfx": true
}
```

Keep voice and pronunciation choices licensed and locally documented. Echodraft does not download models or grant rights to voices automatically.

### 6. Render Segments

Render each segment with `POST /api/v1/projects/{project_id}/segments/{segment_id}/generate`:

```json
{
  "voiceProfileId": "{voice_profile_id}",
  "direction": {
    "scopeType": "segment",
    "scopeId": "{segment_id}",
    "pace": 1.0,
    "intensity": 0.4,
    "tone": "neutral",
    "stylePrompt": "Clear, restrained audiobook narration",
    "emphasis": false,
    "whisper": false,
    "noSfx": true
  },
  "outputFormat": "wav",
  "force": false
}
```

Successful renders are immutable and content-addressed. Repeating an identical request reuses the matching successful render; set `force` to `true` only when a fresh render is intentionally required.

### 7. Assemble a Chapter

After every segment in a chapter has a successful render, call `POST /api/v1/projects/{project_id}/chapters/{chapter_id}/assemble`:

```json
{
  "renderMode": "speech_only"
}
```

Use `speech_only` for the stable alpha workflow. The ambience schema and render modes exist, but real source-asset mixing is still incomplete.

Inspect chapter history with `GET /api/v1/projects/{project_id}/chapters/{chapter_id}/renders` and the selected output with `GET /api/v1/projects/{project_id}/chapters/{chapter_id}/active-render`. Each assembly creates a new manifest-backed record and preserves earlier chapter renders.

### 8. Review and Patch a Line

Create and manage review issues with:

- `GET/POST /api/v1/projects/{project_id}/issues`
- `PATCH /api/v1/issues/{issue_id}`
- `GET/POST /api/v1/issues/{issue_id}/comments`

To correct one line, call `POST /api/v1/projects/{project_id}/segments/{segment_id}/patch`. Supply the revised `textContent` when the words change, the voice and direction to use, and optionally the related `issueId`. The patch operation creates a new segment revision and render, then reassembles only the owning chapter. Previous segment and chapter renders remain available for comparison and rollback analysis.

### 9. Export WAV or MP3

Once the selected chapters have active renders, call `POST /api/v1/projects/{project_id}/exports`:

```json
{
  "format": "mp3",
  "chapterIds": ["{chapter_id}"]
}
```

Use `"wav"` for an uncompressed working export or `"mp3"` for a distributable listening copy. MP3 export requires `ffmpeg` on `PATH`. M4B is not implemented.

The response includes `outputPath` and `manifestPath`. Retain the manifest with the exported audio: it records the selected chapter renders and supports later provenance checks.

### 10. Find Local Project Files

With the default configuration:

- SQLite metadata is stored at `.echodraft/echodraft.db`.
- Project sources, canonical text, manifests, renders, exports, and logs are stored below `.echodraft/projects`.
- Audio files are stored on the filesystem, never as relational database blobs.

The API returns absolute artifact paths for generated records. Do not edit manifests or render history by hand while the API is running. To start from a clean disposable workspace, stop both servers and move the `.echodraft` directory somewhere safe; deleting it permanently removes all local project metadata and artifacts.

### Troubleshooting the Workflow

- If the dashboard cannot connect, verify that the API is running and `NEXT_PUBLIC_API_URL` points to `http://localhost:8000`.
- If an import or extraction appears stuck, inspect its job through `GET /api/v1/jobs/{job_id}`.
- If Kokoro rendering fails, verify the executable, model, voice registry, and requested voice ID; Echodraft does not silently fall back to `mock`.
- If chapter assembly fails, confirm every segment in that chapter has a successful render.
- If MP3 export fails, run `ffmpeg -version` and confirm the installed build includes MP3 encoding support.
- After an unexpected API restart, interrupted in-process jobs are marked failed. Restart the affected operation from its persisted source or render artifacts.

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
