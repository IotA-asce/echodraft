# Getting Started

This guide covers installing, configuring, and running Echodraft locally: system
requirements, platform-specific setup, configuration, TTS modes, PDF OCR,
local data/privacy rules, troubleshooting, and development checks. Once
Echodraft is running, move on to the [production workflow guide](production-workflow.md)
for the step-by-step manuscript-to-export process. See also the
[docs index](../README.md) and the [repository root README](../../README.md).

## System requirements

| Tool                | Supported baseline                        | Purpose                     |
| ------------------- | ----------------------------------------- | --------------------------- |
| Git                 | Current stable                            | Clone and contribute        |
| Python              | 3.12 recommended                          | API and pipeline services   |
| uv                  | Current stable                            | Python workspace management |
| Node.js             | 20 or later                               | Next.js dashboard           |
| npm                 | Bundled with Node.js                      | Frontend dependencies       |
| FFmpeg              | Current stable with MP3 support           | MP3 export                  |
| Poppler + Tesseract | Current stable with English language data | Scanned PDF OCR             |

Python 3.12 is the known project baseline. Newer Python versions may satisfy some metadata but can be incompatible with optional TTS packages.

## Quick start

Clone the repository:

```bash
git clone https://github.com/IotA-asce/echodraft.git
cd echodraft
```

Install Python and frontend dependencies:

```bash
uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

Start the API:

```bash
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

In a second terminal, start the dashboard:

```bash
npm run web:dev
```

Open:

* Dashboard: `http://localhost:3000`
* Interactive API docs: `http://localhost:8000/docs`
* API health: `http://localhost:8000/health`
* Storage readiness: `http://localhost:8000/ready`

## Platform setup

### Windows

Use Windows 10 or 11 and PowerShell.

Install the core tools with Windows Package Manager:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell, then verify:

```powershell
git --version
python --version
node --version
npm --version
uv --version
ffmpeg -version
```

Clone and install:

```powershell
git clone https://github.com/IotA-asce/echodraft.git
Set-Location echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
Copy-Item .env.example .env
```

If `python` opens the Microsoft Store, disable Python app execution aliases in Windows Settings or use `py -3.12`.

### macOS

Install Homebrew if needed, then run:

```bash
brew install git python@3.12 uv node ffmpeg

git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

Apple Silicon works for normal Echodraft development. Optional TTS runtimes choose their own CPU, ONNX, PyTorch, or Metal acceleration strategy.

### Linux

Package names vary by distribution. For Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y git curl ffmpeg

curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Node.js 20 or later from the official Node.js download page or a trusted distribution package.

Then run:

```bash
git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env
```

For Fedora:

```bash
sudo dnf install -y git curl ffmpeg
```

## Configuration

The checked-in `.env.example` documents the default local paths:

```dotenv
ECHODRAFT_DATABASE_URL=sqlite:///./.echodraft/echodraft.db
ECHODRAFT_ARTIFACT_ROOT=./.echodraft/projects
ECHODRAFT_OLLAMA_BASE_URL=http://127.0.0.1:11434
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Next.js reads `NEXT_PUBLIC_API_URL` from `.env`.

The API currently reads settings from the process environment. Defaults work without exporting anything, but you can override them.

PowerShell:

```powershell
$env:ECHODRAFT_DATABASE_URL = "sqlite:///./.echodraft/echodraft.db"
$env:ECHODRAFT_ARTIFACT_ROOT = ".\.echodraft\projects"
$env:ECHODRAFT_TTS_PROVIDER = "mock"
$env:ECHODRAFT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
```

Bash/zsh:

```bash
export ECHODRAFT_DATABASE_URL='sqlite:///./.echodraft/echodraft.db'
export ECHODRAFT_ARTIFACT_ROOT='./.echodraft/projects'
export ECHODRAFT_TTS_PROVIDER='mock'
export ECHODRAFT_OLLAMA_BASE_URL='http://127.0.0.1:11434'
```

Do not enter Bash-style `NAME=value` commands directly into PowerShell. Use `$env:NAME = "value"`.

## Running Echodraft

Start the API from the repository root:

```bash
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload
```

Start the dashboard in another terminal:

```bash
npm run web:dev
```

Health checks:

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Linux/macOS:

```bash
curl http://localhost:8000/health
```

## TTS modes

### Mock TTS

Mock TTS is recommended for the first run.

PowerShell:

```powershell
$env:ECHODRAFT_TTS_PROVIDER = "mock"
```

Bash/zsh:

```bash
export ECHODRAFT_TTS_PROVIDER=mock
```

Mock TTS creates deterministic silent 16 kHz WAV files. It validates the production pipeline but does not produce spoken narration.

### Managed Kokoro setup

Real Kokoro synthesis can be set up from the dashboard.

Open **Voice setup**, choose **Kokoro managed preset voice system**, then select **Download and install Kokoro locally**.

The setup job handles:

* local Python runtime creation;
* package installation;
* model download;
* voice data download;
* fixed preset voice list generation;
* preview validation;
* settings save.

Managed setup stores files under:

```text
.echodraft/kokoro/managed-onnx-v1
```

The current managed path is CPU-oriented and exposes selectable Kokoro preset voice IDs. It does not create new custom voices; custom voice support belongs to other local providers such as imported Piper models or consent-gated XTTS-v2 reference voices. GPU/provider tuning remains out of scope for this release.

The setup job uses network access only after you select the install button. Manuscripts, generated audio, and project metadata are not uploaded.

Managed Kokoro synthesis uses a resident local worker when configured through the app. The worker loads the model once per API process, serializes synthesis requests, restarts once on failure, and exposes runtime status at `GET /api/v1/settings/tts/worker`.

### Advanced custom Kokoro adapter

The dashboard also exposes an advanced custom adapter path for users who already maintain a compatible wrapper.

Echodraft expects an executable that accepts:

```text
--model
--voices
--voice
--text
--output
```

The executable must:

1. return exit code `0` on success;
2. write a non-empty valid WAV file to `--output`;
3. use the supplied model path;
4. read a UTF-8 voice registry containing one allowed voice ID per line;
5. reject voices not present in the registry.

Echodraft never silently falls back from Kokoro to mock. If Kokoro is configured incorrectly, startup or synthesis fails with recovery guidance.

### Piper fallback and XTTS-v2 opt-in

Stage 9 adds a formal local provider registry. Piper can be configured with a local executable, ONNX model, optional config, and optional voice registry. XTTS-v2 can be configured with a local Python runtime, reference WAV, language, and explicit reference-voice consent.

Both providers fail closed when required local files or consent are missing. Echodraft does not upload text, voices, or generated audio and does not silently switch providers.

Production render fingerprints now include provider identity, synthesis text after pronunciation replacements, and applied pronunciation entries. Provider, pronunciation, voice, direction, or text changes stale only affected segment renders.

## PDF OCR

Text-based PDFs are extracted directly.

Scanned or image-only PDFs require local Poppler and Tesseract English OCR.

macOS:

```bash
brew install poppler tesseract
```

Debian/Ubuntu:

```bash
sudo apt install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

Windows users can install Poppler and the UB Mannheim Tesseract build, then add both executable directories to `PATH`.

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

PDF OCR is local. It does not upload manuscript pages.

Current limits:

* OCR is attempted only on low-text pages;
* OCR renders pages at 200 DPI;
* imports needing OCR on more than 150 pages are rejected;
* password-protected PDFs are not supported.

## Local data and privacy

Default storage:

| Data                  | Default location                    |
| --------------------- | ------------------------------------ |
| SQLite metadata       | `.echodraft/echodraft.db`           |
| Project artifacts     | `.echodraft/projects`               |
| Managed Kokoro files  | `.echodraft/kokoro/managed-onnx-v1` |
| Source originals      | Project artifact directories        |
| Segment/chapter audio | Project artifact directories        |
| Exports/manifests     | Project artifact directories        |

Important rules:

* Audio binaries are never stored in the relational database.
* Source files, generated audio, manifests, and exports remain local.
* Do not edit manifests or render history by hand while the API is running.
* `test-assets/` is intentionally ignored by Git.
* Keep private manuscripts, converted PDFs, and local-only fixtures out of Git.

## Troubleshooting

### `uv sync` removes FastAPI or workspace packages

Recreate the environment with all workspace packages.

PowerShell:

```powershell
Remove-Item -Recurse -Force .venv
uv sync --python 3.12 --all-packages --group dev
```

Bash/zsh:

```bash
rm -rf .venv
uv sync --python 3.12 --all-packages --group dev
```

### PowerShell rejects `NAME=value`

Use:

```powershell
$env:NAME = "value"
```

Bash/zsh use:

```bash
export NAME=value
```

### Dashboard cannot reach the API

Confirm the API is running:

```bash
curl http://localhost:8000/health
```

Confirm `.env` contains:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Restart the dashboard after changing any `NEXT_PUBLIC_*` variable.

### Import or extraction appears stuck

Inspect the job endpoint:

```text
GET /api/v1/jobs/{job_id}
```

Failed jobs include `errorMessage`.

Jobs interrupted by an API restart are marked failed and should be restarted from persisted inputs.

### Chapter assembly fails

Every segment in the chapter must have a successful active render before the chapter can be assembled.

### MP3 export fails

Run:

```bash
ffmpeg -version
```

Confirm the build includes an MP3 encoder such as `libmp3lame`.

### Kokoro fails before synthesis

Verify:

```text
executable exists and is runnable
model path exists
voice registry exists and is UTF-8 text
requested voice ID is in the registry
wrapper writes a valid non-empty WAV
```

## Development checks

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

Repo operating constraints and the full branch/verify/commit/merge/push workflow live in [`../../AGENTS.md`](../../AGENTS.md).

Once the app is running, continue with the [production workflow guide](production-workflow.md).
