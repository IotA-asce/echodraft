<div align="center">

# Echodraft

**Turn any book into a multi-voice audiobook. Entirely on your machine.**

[![CI](https://github.com/IotA-asce/echodraft/actions/workflows/ci.yml/badge.svg)](https://github.com/IotA-asce/echodraft/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-black.svg)](pyproject.toml)
[![Node 20+](https://img.shields.io/badge/Node-20%2B-black.svg)](package.json)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-black.svg)](CONTRIBUTING.md)

[Vision](#the-vision) · [How it works](#how-it-works) · [Quick start](#quick-start) · [Roadmap](#roadmap) · [Contributing](#contributing) · [Docs](docs/README.md)

</div>

---

Echodraft is a **local-first AI audiobook production studio**. Drop in a rights-cleared manuscript — PDF, EPUB, DOCX, Markdown, or plain text — and it understands the book: chapters, scenes, characters, who speaks which line, and how each line should be delivered. Then it casts voices, narrates every segment, mixes and masters chapter audio, and packages a chaptered audiobook you can export as WAV, MP3, or M4B.

Everything runs on your hardware. Your manuscripts, voices, and audio never leave your machine — unless you explicitly opt in: bring-your-own-key [cloud LLM providers](docs/architecture/local-ai/cloud-llm-providers.md) are available strictly behind a consent gate, and local stays the default.

![Review, patch, and export workflow](docs/assets/review-patch-export.gif)

## Why this exists

Producing an audiobook today means either hiring a studio, or feeding text into a one-shot TTS tool and living with whatever comes out. Echodraft takes a third path: treat audiobook production as an **editable, inspectable pipeline** built on one rule —

> **A segment is the smallest editable, renderable, reviewable, and patchable unit.**

Fixing one bad line never means regenerating a chapter or losing history. Every render is append-only, every automated decision keeps its evidence, and every stage writes a durable manifest you can inspect.

| One-shot TTS tools | Echodraft |
| --- | --- |
| Paste text, get audio | Understand → cast → direct → narrate → mix → review → export |
| Re-render large chunks to fix one line | Re-render exactly one segment |
| Black-box output | Evidence trails, manifests, append-only render lineage |
| Cloud-first, upload your book | Local-first — nothing leaves your machine unless you explicitly opt in to a cloud LLM |
| Single narrator voice | Multi-voice cast with per-character voices and delivery direction |

## The vision

Where this project is headed — and where we want collaborators:

**A book goes in. A finished audiobook comes out. You only touch what you *want* to change.**

- **Zero-touch by default.** Character discovery, speaker attribution, voice casting, performance direction, and sound design all happen automatically — with calibrated confidence, evidence trails, and a handful of meaningful review tasks instead of thousands of flags.
- **Voices that perform, not just read.** Emotion-aware, production-grade TTS: anger, whispers, laughter, grief — with a unique, consistent, synthesized voice for every character.
- **A living soundtrack.** Ambient beds, sparse SFX, and restrained music generated locally and placed automatically from each scene's atmosphere — conservative and tasteful by design.
- **An app for everyone, everywhere.** Windows, macOS, Linux — then Android and iOS. Every dependency and model downloaded and managed by the app itself. No terminal required.
- **Minimal, monochrome UI.** Two colors, thin type, only necessary motion. The book is the star.
- **Local-first, forever.** No mandatory cloud, no uploads, no accounts. Optional bring-your-own-key cloud LLM providers exist today — strictly opt-in, never required.

This isn't hand-waving: the complete target product is already designed in a **15-document engineering blueprint** — architecture, algorithms, data model, API contracts, UI spec, evaluation harness, and a workstream-by-workstream [implementation roadmap](docs/plans/v2-implementation-roadmap.md). Start at [`docs/README.md`](docs/README.md).

## How it works

```text
 Manuscript (PDF / EPUB / DOCX / MD / TXT)
     │
     ▼
 ┌─────────────────────────────────────────────────────────┐
 │  UNDERSTAND   ingest · OCR · clean · chapters · scenes  │
 │               segments · characters · speaker per line  │
 ├─────────────────────────────────────────────────────────┤
 │  DIRECT       emotion · pace · pauses · delivery        │
 ├─────────────────────────────────────────────────────────┤
 │  CAST         voice profiles · narrator · per-character │
 ├─────────────────────────────────────────────────────────┤
 │  PRODUCE      segment TTS · chapter assembly · ambience │
 │               mixing · mastering (−19 LUFS / −3 dBTP)   │
 ├─────────────────────────────────────────────────────────┤
 │  REVIEW       transcript · waveform · QA issues ·       │
 │               patch one line · re-render one segment    │
 ├─────────────────────────────────────────────────────────┤
 │  EXPORT       WAV · MP3 · M4B with chapters, metadata,  │
 │               lineage, checksums                        │
 └─────────────────────────────────────────────────────────┘
     │
     ▼
 Chaptered audiobook package
```

Under the hood: a **Next.js** dashboard talks to a **FastAPI** engine. **SQLite** holds metadata; audio artifacts and stage manifests live on the filesystem. Local runtimes do the heavy lifting — **Ollama** for book understanding, **Kokoro / Piper / XTTS-v2** for synthesis, **ffmpeg** for mastering and packaging. Audio blobs never touch the database, and render history is append-only.

| | |
| --- | --- |
| ![Project dashboard](docs/assets/dashboard-projects.png) | ![Manuscript import](docs/assets/manuscript-import.png) |
| ![Voice setup](docs/assets/voice-setup.png) | ![Segment editor](docs/assets/segment-editor.png) |

## What works today

Echodraft is a **working alpha** — the full local production loop is implemented end-to-end:

- Import TXT / Markdown / DOCX / EPUB / PDF, with page-aware OCR for scanned PDFs
- Deterministic structure extraction into chapters → scenes → segments, with parser evidence and optional local-LLM refinement
- Automatic cast discovery, a Character Bible with aliases/traits/merge history, and speaker attribution with review locks
- Direction Studio: per-segment emotion, pace, intensity, and pause controls with inferred defaults
- Local TTS providers: managed Kokoro ONNX (installed from the dashboard), Piper, consent-gated XTTS-v2, and a mock provider for pipeline validation
- Segment-level rendering with content-hash caching, immutable chapter assembly, ambience/music/SFX mixing, and loudness-normalized mastering
- A review workbench: transcript timeline, waveform issue markers, audio QA (including optional local ASR verification), comments, and one-line patching
- Export to WAV, MP3, and M4B with chapter markers, metadata, QA scorecards, and render lineage
- A Model Center that installs and verifies local tools and models with explicit consent

**The v2 engine has landed behind feature flags** (default-off until they pass real-corpus quality gates): parallelized, checkpoint-resumable extraction with an inference cache; embedding-clustered cast discovery; LLM-primary speaker attribution with self-consistency voting; fully automatic voice casting with a measured voice catalog, narrator selection, and a constraint-relaxation solver; procedural (Tier-0) ambience/SFX/music planned and placed automatically from per-scene atmosphere profiles; a live SSE job-event stream; and a monochrome token-based UI with virtualized lists and query-driven polling.

**Known honest gaps**: the v2 quality gates have only run on synthetic fixtures so far (real-corpus certification is the V3 "Prove" arc), expressive emotion doesn't yet reach a synthesizer (needs the GPU bake-off), generative audio models aren't integrated (procedural tier only), and desktop/mobile packaging hasn't started. Every gap has a design doc and a scheduled workstream — see the [V3 plan](docs/plans/v3-plan.md).

## Quick start

Requires [Python 3.12](https://www.python.org/) + [uv](https://docs.astral.sh/uv/), [Node 20+](https://nodejs.org/), and optionally [ffmpeg](https://ffmpeg.org/) for MP3/M4B export.

```bash
git clone https://github.com/IotA-asce/echodraft.git
cd echodraft

uv python install 3.12
uv sync --python 3.12 --all-packages --group dev
npm install
cp .env.example .env

# terminal 1 — engine
uv run --package echodraft-api uvicorn echodraft_api.main:app --reload

# terminal 2 — dashboard
npm run web:dev
```

Open **http://localhost:3000**, create a project, import a manuscript, and start with the mock TTS provider to validate the whole pipeline before downloading a voice model.

Full setup (Windows/macOS/Linux specifics, TTS providers, OCR, configuration, troubleshooting): **[Getting Started guide](docs/guides/getting-started.md)** · step-by-step usage: **[Production Workflow guide](docs/guides/production-workflow.md)**

## Roadmap

The target product is fully specified in the [v2 documentation suite](docs/README.md), sequenced in the [v2 implementation roadmap](docs/plans/v2-implementation-roadmap.md), and carried forward by the [V3 plan](docs/plans/v3-plan.md) (three arcs: **Prove** real-corpus quality and graduate the flags, **Perform** expressive TTS and generative sound, **Ship** desktop and mobile apps). Workstream status:

| # | Workstream | Design doc | Status |
| --- | --- | --- | --- |
| W0 | UI performance quick wins (kill the freezes) | [frontend-architecture](docs/ui/frontend-architecture.md) | ✅ Landed |
| W1 | Quality evaluation baseline (golden corpus, metrics) | [quality-evaluation-v2](docs/pipeline/qa/quality-evaluation-v2.md) | ✅ Landed (synthetic baseline; real-corpus runs are V3) |
| W2 | Parallel, resumable pipeline orchestrator | [target-architecture](docs/architecture/target-architecture.md) | ✅ Landed |
| W3 | LLM-first extraction — hours → minutes, minimal flags | [extraction-pipeline-v2](docs/architecture/extraction-pipeline-v2.md) | ✅ Landed (flag-gated) |
| W4 | Fully automatic voice casting | [automatic-casting-v2](docs/pipeline/casting/automatic-casting-v2.md) | ✅ Landed (flag-gated) |
| W5 | Expressive, emotion-aware TTS + voice synthesis | [tts-engine-strategy](docs/pipeline/tts/tts-engine-strategy.md) | 🔶 Engine host + honest direction compiler landed; Tier-S bake-off needs GPU hardware |
| W6 | AI-generated ambience, SFX, and music | [generative-sound-design](docs/pipeline/assembly/generative-sound-design.md) | 🔶 Procedural Tier-0 landed; generative tier open |
| W7 | Monochrome UI overhaul | [design-system](docs/ui/design-system.md) | 🔶 Tokens, primitives, monochrome theme, virtualization landed; route extraction open |
| W8 | Desktop apps with self-contained dependencies | [cross-platform-strategy](docs/platform/cross-platform-strategy.md) | ⬜ Open (V3) |
| W9 | Mobile apps | [cross-platform-strategy](docs/platform/cross-platform-strategy.md) | ⬜ Open (V3) |

Milestones: **M1** sub-hour extraction of a 500-page book → **M2** zero-touch book (upload → export with no required steps) → **M3** first signed desktop installer → **M4** phone playback of a desktop-produced book. M1/M2 mechanics are in place; certifying them on real books is [V3 Arc 1](docs/plans/v3-plan.md).

## Contributing

Contributions are very welcome — this project is intentionally designed so people can pick up well-scoped work:

- **Code:** every roadmap workstream is broken into feature-branch-sized tasks with entry/exit criteria. Pick one from the [roadmap](docs/plans/v2-implementation-roadmap.md).
- **Not just code:** golden-corpus labeling, blind listening evaluations, and TTS/audio model bake-offs on varied hardware (especially GPUs, Apple Silicon, and low-end machines) are first-class contributions here.
- **Docs & design:** the v2 suite thrives on review — find a hole in an algorithm, challenge a model choice, improve a spec.

Read **[CONTRIBUTING.md](CONTRIBUTING.md)** for setup, the branch/verification workflow, and PR guidelines. Be excellent to each other per the [Code of Conduct](CODE_OF_CONDUCT.md).

## Rights & responsibility

Echodraft is a production tool, not a rights workaround. It requires an explicit rights declaration per project and is meant for **your own manuscripts, licensed work, and the public domain**. It is not a voice marketplace, does not clone voices without consent, and never uploads your content anywhere.

## License

[MIT](LICENSE) © 2026 Mu In Nasif
