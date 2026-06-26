# echodraft

`echodraft` is a local-first AI audiobook production system. It turns a rights-cleared manuscript into editable chapters, scenes, segments, immutable voice renders, chapter stems, review patches, and export packages.

The system is deliberately segment-first and manifest-driven:

- a segment is the smallest editable and renderable unit;
- source files, manifests, audio, and exports remain on the local filesystem;
- render history is append-only;
- correcting one line rerenders that segment and its owning chapter instead of regenerating the whole book.

> **Alpha software:** the dashboard covers the supported local production workflow from manuscript intake through chapter export. Real Kokoro TTS can be set up locally from the dashboard using the managed Kokoro ONNX flow.

## Capabilities

- SQLite-backed local project metadata and filesystem-backed artifacts.
- TXT, Markdown, DOCX, EPUB, and PDF manuscript ingestion.
- Preserved originals, canonical text, parser warnings, and import manifests.
- Chapter, scene, and sentence-safe segment extraction.
- Inline segment editing with immutable revision history.
- Character, voice-profile, pronunciation, and direction records.
- Deterministic mock TTS for pipeline development.
- Managed local Kokoro ONNX setup plus advanced bring-your-own adapter support.
- Immutable segment renders and manifest-backed chapter assembly.
- Review issues, comments, selective line patching, and chapter reassembly.
- WAV and MP3 export packages with manifests and checksums.
- Startup reconciliation for interrupted in-process jobs.

## Current limitations

- The default `mock` TTS provider creates silent WAV files. It validates the production workflow but does not produce spoken audio.
- Kokoro models, voices, and inference runtimes are not bundled; the dashboard downloads them only when the user starts managed Kokoro setup.
- Managed Kokoro setup is CPU-oriented. GPU/provider tuning remains out of scope.
- The dashboard covers project creation, manuscript intake, structure browsing, voice setup, chapter production, review, patching, and WAV/MP3 export. The API documentation remains available for development and integration work.
- Ambience schemas and render modes exist, but source-asset mixing and dashboard controls are incomplete.
- WAV and MP3 exports are implemented. M4B is not.
- Text-based PDFs are extracted directly. Scanned PDFs require local Poppler and Tesseract English OCR; imports OCR at most 150 low-text pages.

## System requirements

| Tool | Supported baseline | Purpose |
| --- | --- | --- |
| Git | Current stable | Clone and contribute |
| Python | 3.12 recommended | API and pipeline services |
| [uv](https://docs.astral.sh/uv/) | Current stable | Python/workspace management |
| Node.js | 20 or later | Next.js dashboard |
| npm | Bundled with Node.js | Frontend dependencies |
| FFmpeg | Current stable with MP3 support | MP3 export |
| Poppler + Tesseract | Current stable with English language data | Scanned PDF OCR |

Python 3.12 is the known project baseline. Newer Python versions may satisfy the workspace metadata but can be incompatible with optional TTS packages. In particular, current Kokoro runtimes commonly require Python 3.12 or earlier.

## Install on Windows

Use Windows 10 or 11 and PowerShell. Windows Package Manager is the simplest option:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell, then verify the tools:

```powershell
git --version
python --version
node --version
npm --version
uv --version
ffmpeg -version
```

If `python` opens the Microsoft Store, disable the Python app execution aliases in Windows Settings or use `py -3.12` to verify the installation.

Clone and install Echodraft:

```powershell
git clone https://github.com/IotA-asce/echodraft.git
Set-Location echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
Copy-Item .env.example .env
```

The `--all-packages` flag is required. Without it, `uv sync` can install only the root development tools and remove the API workspace packages.

## Install on macOS

Install [Homebrew](https://brew.sh/) if necessary, then run:

```bash
brew install git python@3.12 uv node ffmpeg

git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

Apple Silicon works for normal Echodraft development. Optional Kokoro runtimes choose their own CPU, ONNX, PyTorch, or Metal acceleration strategy.

## Install on Linux

Package names vary by distribution. The Debian/Ubuntu example is:

```bash
sudo apt update
sudo apt install -y git curl ffmpeg

curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Node.js 20 or later from the [official Node.js download page](https://nodejs.org/en/download) or a trusted distribution package that provides a sufficiently recent version. Reopen the terminal if the `uv` installer changes `PATH`, then run:

```bash
git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

Fedora users can install the system tools with:

```bash
sudo dnf install -y git curl ffmpeg
```

## Configure the local workspace

The checked-in `.env.example` contains the frontend URL and documents the default local paths:

```dotenv
ECHODRAFT_DATABASE_URL=sqlite:///./.echodraft/echodraft.db
ECHODRAFT_ARTIFACT_ROOT=./.echodraft/projects
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Next.js reads `NEXT_PUBLIC_API_URL` from `.env`. The API currently reads its settings from the process environment; it does not automatically load `.env`.

The defaults work without exporting anything. To override them for the current PowerShell session:

```powershell
$env:ECHODRAFT_DATABASE_URL = "sqlite:///./.echodraft/echodraft.db"
$env:ECHODRAFT_ARTIFACT_ROOT = ".\.echodraft\projects"
$env:ECHODRAFT_TTS_PROVIDER = "mock"
```

The Bash/zsh equivalent is:

```bash
export ECHODRAFT_DATABASE_URL='sqlite:///./.echodraft/echodraft.db'
export ECHODRAFT_ARTIFACT_ROOT='./.echodraft/projects'
export ECHODRAFT_TTS_PROVIDER='mock'
```

Do not enter Bash-style `NAME=value` commands directly into PowerShell. PowerShell environment variables use `$env:NAME = "value"`.

## Run Echodraft

Start the API from the repository root:

```bash
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

Start the dashboard in a second terminal:

```bash
npm run web:dev
```

Open:

- Dashboard: `http://localhost:3000`
- Interactive API: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`
- Storage readiness: `http://localhost:8000/ready`

PowerShell health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Linux/macOS health check:

```bash
curl http://localhost:8000/health
```

## Production workflow

### 1. Create a project

In the dashboard, enter a title and optional author, confirm that you have the rights to produce the audiobook, and select **Create project**. Echodraft rejects projects without a declared rights status.

### 2. Import a manuscript

Open the project and choose a `.txt`, `.md`, `.markdown`, `.docx`, `.epub`, or `.pdf` file. The dashboard accepts files up to 10 MB.

Echodraft preserves the original, creates canonical text, and reports parser warnings. Review the preview before continuing. Use **Reparse** to repeat normalization from the preserved source.

Text-based PDFs are extracted directly. For scanned or image-only pages, Echodraft renders only the low-text pages at 200 DPI and OCRs them locally with Tesseract English. Install the local tools before importing scanned PDFs:

```bash
# macOS
brew install poppler tesseract

# Debian/Ubuntu
sudo apt install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

Windows users can install Poppler and the UB Mannheim Tesseract build, then add both executable directories to `PATH`. PDF OCR never uploads manuscript pages and rejects imports needing OCR on more than 150 pages. Password-protected PDFs are not supported.

```powershell
# Windows: install Tesseract, then install a Poppler distribution and add its Library\bin folder to PATH.
winget install --id UB-Mannheim.TesseractOCR
```

Import and reparse operations return background jobs. In the API, poll `GET /api/v1/jobs/{job_id}` until the job is `succeeded`, `failed`, or `cancelled`.

### 3. Extract structure

Select **Extract structure**. The default maximum segment size is 600 characters. The hierarchy can also be queried through:

1. `GET /api/v1/projects/{project_id}/chapters`
2. `GET /api/v1/chapters/{chapter_id}/scenes`
3. `GET /api/v1/scenes/{scene_id}/segments`

Markdown headings such as `## Chapter 1` produce the best chapter boundaries.

### 4. Edit segments

Select a segment to open the inline multiline editor. It displays the next revision number, character count, save/cancel controls, validation feedback, and unsaved-change protection.

- `Ctrl+Enter` or `Cmd+Enter`: save a new revision
- `Esc`: cancel the edit

Saving never overwrites history. Previous text is available from `GET /api/v1/segments/{segment_id}/revisions`.

### 5. Configure voices in the dashboard

Open **Voice setup** in the selected project. Choose `mock` to exercise the pipeline with silent WAVs, or choose **Kokoro managed voice system** and select **Download and install Kokoro locally**. The dashboard creates the local runtime, downloads Kokoro ONNX assets, builds the voice list, validates a preview, and then exposes available voices as selectable cards.

Preview a voice and choose one stable narrator for the project. Segment-level voice overrides are available from the structure view. Character and pronunciation records are retained in the voice bible as editorial reference; current alpha synthesis does not automatically apply them.

### 6. Produce, review, and export in the dashboard

Select a chapter, then choose **Produce chapter**. Echodraft renders only missing or stale segments, assembles a new immutable speech-only chapter render, and exposes a local audio player. **Force regenerate** creates fresh render lineage even when the source and settings are unchanged.

Use **Review & patch** to read automated QA findings, leave local comments, resolve issues, and selectively patch a segment before rebuilding its owning chapter. Select one or more chapters under **Export** to create a WAV or MP3 ZIP package. Every ZIP contains only the active render per selected chapter plus an export manifest and checksum data.

## TTS modes

### Mock TTS: recommended first run

Mock TTS is built in and requires no model download:

```powershell
$env:ECHODRAFT_TTS_PROVIDER = "mock"
```

```bash
export ECHODRAFT_TTS_PROVIDER=mock
```

It creates deterministic silent 16 kHz WAV files. Use it to validate ingestion, rendering, assembly, patching, and export before introducing a real model.

### Kokoro managed setup

Real Kokoro synthesis is set up from the dashboard. Open **Voice setup**, choose **Kokoro managed voice system**, and select **Download and install Kokoro locally**. The API starts a local setup job with progress for Python runtime creation, package install, model download, voice data download, voice list generation, preview validation, and settings save.

Managed setup stores files under `.echodraft/kokoro/managed-onnx-v1` by default:

- a local Python virtual environment;
- `kokoro-onnx==0.4.7` and `soundfile`;
- `kokoro-v1.0.onnx`;
- `voices-v1.0.bin`;
- an Echodraft helper script;
- `voices.txt`, generated from the local Kokoro ONNX voice list.

The managed path is CPU-oriented for this release. GPU/provider tuning remains out of scope. The setup job uses network access only after the user selects the install button. Manuscripts, generated audio, and project metadata are not uploaded.

If setup fails, the dashboard shows one recovery action. Use **Repair setup** after checking network access, disk space, and whether the Python environment can create virtual environments and install wheels.

### Advanced custom Kokoro adapter

The dashboard still has an **Advanced custom adapter** section for users who already maintain a compatible wrapper. Echodraft expects an executable that accepts this exact command:

```text
<executable> --model <model-path> --voices <registry.txt> --voice <voice-id> --text <text> --output <output.wav>
```

Requirements:

1. The command must return exit code `0` on success.
2. It must write a non-empty, valid WAV file to `--output`.
3. `--model` points to the model used for synthesis.
4. `--voices` points to a UTF-8 text registry containing one allowed voice ID per line.
5. The requested `--voice` must appear in that registry.

`voices-v1.0.bin` from `kokoro-onnx` is binary model data, not Echodraft's text registry. A wrapper must know where the binary voice data lives and translate Echodraft's command contract into the selected Kokoro runtime's Python or CLI API.

Common upstream commands such as the third-party [`kokoro-tts`](https://github.com/nazdridoy/kokoro-tts) CLI use positional input/output files and keep ONNX assets in their working directory. They cannot be assigned directly to `ECHODRAFT_KOKORO_EXECUTABLE` unless wrapped to implement the contract above.

Once a compatible wrapper exists, create a registry such as:

```text
# Locally approved Kokoro voice IDs
af_heart
af_sarah
am_adam
```

Test the wrapper independently before starting Echodraft.

PowerShell example:

```powershell
& "C:\Tools\echodraft-kokoro.exe" `
  --model "$HOME\.local\share\echodraft\kokoro\kokoro-v1.0.onnx" `
  --voices "$HOME\.local\share\echodraft\kokoro\voices.txt" `
  --voice "af_heart" `
  --text "Echodraft Kokoro test." `
  --output "$env:TEMP\echodraft-kokoro-test.wav"
```

Linux/macOS example:

```bash
/usr/local/bin/echodraft-kokoro \
  --model "$HOME/.local/share/echodraft/kokoro/kokoro-v1.0.onnx" \
  --voices "$HOME/.local/share/echodraft/kokoro/voices.txt" \
  --voice af_heart \
  --text "Echodraft Kokoro test." \
  --output /tmp/echodraft-kokoro-test.wav
```

Configure Echodraft only after that command succeeds.

Windows PowerShell:

```powershell
$env:ECHODRAFT_TTS_PROVIDER = "kokoro"
$env:ECHODRAFT_KOKORO_EXECUTABLE = "C:\Tools\echodraft-kokoro.exe"
$env:ECHODRAFT_KOKORO_MODEL_PATH = "$HOME\.local\share\echodraft\kokoro\kokoro-v1.0.onnx"
$env:ECHODRAFT_KOKORO_VOICE_PATH = "$HOME\.local\share\echodraft\kokoro\voices.txt"
```

Linux/macOS:

```bash
export ECHODRAFT_TTS_PROVIDER=kokoro
export ECHODRAFT_KOKORO_EXECUTABLE=/usr/local/bin/echodraft-kokoro
export ECHODRAFT_KOKORO_MODEL_PATH="$HOME/.local/share/echodraft/kokoro/kokoro-v1.0.onnx"
export ECHODRAFT_KOKORO_VOICE_PATH="$HOME/.local/share/echodraft/kokoro/voices.txt"
```

Echodraft fails with recovery guidance if the executable, model, registry, requested voice, or resulting WAV is invalid. It never silently falls back from Kokoro to mock.

### Kokoro direction limitations

The current adapter records direction fields in manifests, but the CLI call only guarantees model, voice, text, and output. Pace, intensity, tone, emphasis, and whisper are not reliably applied to synthesis yet. Treat real Kokoro support as an integration foundation, not a finished voice-direction system.

## Local data and privacy

Default storage:

- SQLite metadata: `.echodraft/echodraft.db`
- Project artifacts: `.echodraft/projects`
- Source originals: project artifact directories
- Segment and chapter audio: project artifact directories
- Exports and manifests: project artifact directories

Audio binaries are never stored in the relational database. Do not edit manifests or render history by hand while the API is running.

`test-assets/` is intentionally ignored by Git. Keep private manuscripts, converted PDFs, and local-only fixtures there; never stage or commit them.

## Troubleshooting

### `Set-Location echodraft` fails on Windows

Check the prompt. If it already ends in `\echodraft>`, you are already inside the repository and should not enter the directory again.

### `uv sync` removes FastAPI and workspace packages

Recreate the environment with all workspace packages:

```powershell
Remove-Item -Recurse -Force .venv
uv sync --python 3.12 --all-packages --group dev
```

```bash
rm -rf .venv
uv sync --python 3.12 --all-packages --group dev
```

### PowerShell rejects `NAME=value`

Use `$env:NAME = "value"`. Bash/zsh use `export NAME=value`.

### Dashboard cannot reach the API

Confirm the API is running and `.env` contains:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart the dashboard after changing a `NEXT_PUBLIC_*` variable.

### Import or extraction appears stuck

Inspect `GET /api/v1/jobs/{job_id}`. Failed jobs include `errorMessage`. Jobs interrupted by an API restart are marked failed and should be restarted from persisted inputs.

### Chapter assembly fails

Every segment in the chapter must have a successful render.

### MP3 export fails

Run `ffmpeg -version` and confirm the build includes an MP3 encoder such as `libmp3lame`.

### Kokoro fails before synthesis

Verify:

```text
executable exists and is runnable
model path exists
voice registry exists and is UTF-8 text
requested voice ID is in the registry
wrapper writes a valid non-empty WAV
```

## Development and verification

Run backend checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/domain-models/src libs/db/src
```

Run frontend checks:

```bash
npm run web:lint
npm run web:typecheck
```

Install the Playwright browser once, then run the smoke test:

```bash
npx playwright install chromium
npm run web:test:smoke
```

Check migrations against a disposable database when persistence changes.

PowerShell:

```powershell
$env:ECHODRAFT_DATABASE_URL = "sqlite:///./.tmp/echodraft-migration.db"
uv run alembic -c libs/db/alembic.ini upgrade head
Remove-Item Env:ECHODRAFT_DATABASE_URL
```

Linux/macOS:

```bash
ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db \
  uv run alembic -c libs/db/alembic.ini upgrade head
```

## Repository layout

| Path | Responsibility |
| --- | --- |
| `apps/api` | FastAPI application and pipeline services |
| `apps/web` | Next.js local dashboard |
| `libs/domain-models` | Shared Pydantic API/domain models |
| `libs/db` | SQLAlchemy repositories and Alembic migrations |
| `docs` | Architecture, product, API, and operating specifications |
| `plans` | Roadmap and execution plans |
| `implement` | Stage-by-stage implementation briefs |
| `test-assets` | Ignored local-only fixtures; never committed |

## Engineering rules

- Keep changes modular and local-first.
- Preserve append-only segment and chapter render history.
- Never put audio blobs in SQLite or another relational database.
- Treat segments as the atomic editable and renderable unit.
- Update manifests whenever pipeline inputs or outputs change.
- Follow the branch, verification, commit, merge, and push workflow in [AGENTS.md](AGENTS.md).

See [docs/README.md](docs/README.md) for the documentation map, [docs/alpha-operations.md](docs/alpha-operations.md) for operating guidance, and [LICENSE](LICENSE) for repository licensing.
