# Cross-Platform Strategy

This document specifies how Echodraft ships as a **self-contained app on Windows, macOS,
Linux, Android, and iOS** — every dependency downloaded and managed by the app itself, with
no manual `brew`/`winget`/`apt` install and no system-installed poppler, tesseract, ffmpeg,
or Ollama. It is the "how it runs on a real machine" companion to the architecture and
pipeline docs; it does not change pipeline behavior, only where and how the existing engine
and UI execute.

Related docs:

- [`../product/product-vision-v2.md`](../product/product-vision-v2.md) — north-star vision;
  defines Phase D (desktop packaging) and Phase E (mobile) at the vision level and points here
  for the mechanics.
- [`../architecture/target-architecture.md`](../architecture/target-architecture.md) — the
  engine/UI split and resumable job DAG that make packaging the engine as a standalone local
  service possible in the first place.
- [`../pipeline/tts/tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md) — engine
  tiering per hardware; should consume the hardware tiers defined in §9 here rather than
  redefining them.
- [`../ui/frontend-architecture.md`](../ui/frontend-architecture.md) — the Next.js
  re-architecture (real routes, event push) this doc assumes when deciding how the UI is
  hosted inside a desktop/mobile shell.
- [`../architecture/local-ai/model-center.md`](../architecture/local-ai/model-center.md) —
  the current dependency/model catalog this doc evolves into a fully self-contained v2
  download manager (§5).
- [`../product/platform-evolution.md`](../product/platform-evolution.md) — the *hosted,
  multi-tenant* evolution path (publisher/studio modes, Postgres, worker fleets). That doc and
  this one are orthogonal: this one is about running the existing single-node, local-first
  product on more device form factors, not about server-side scale-out.

---

## 1. Purpose, goals, non-goals

### Purpose

Define a concrete, honest packaging and dependency strategy so Echodraft can be installed by
a non-technical user on any of five platforms and immediately produce audiobooks, with the
app itself responsible for acquiring every binary and model it needs.

### Goals

1. **Zero manual dependency installation.** No user, on any platform, ever runs a package
   manager, installs Python, or starts a background service by hand. Today's
   `apps/api/src/echodraft_api/system_tools.py` (PATH lookup + winget-path guessing) and
   `model_catalog.yaml`'s `system_tool` install type (`brew`/`apt`/`winget`) are the pattern
   being replaced, not extended.
2. **One installer per desktop OS; one store package per mobile OS.** A user downloads one
   artifact and has a working app.
3. **The full production pipeline runs entirely on-device on desktop** (Windows/macOS/Linux),
   with no mandatory network calls once dependencies are installed — consistent with the
   local-first constraint that already governs the codebase.
4. **Mobile ships an honest, narrower slice first**, not a compromised attempt at full parity
   (see §2, §6).
5. **App updates never invalidate existing render history.** Shell, engine, and model versions
   are independent (§8), building on the render-fingerprinting that already exists (segment
   render identity already includes "active TTS provider identity and model version" per
   [`tts-production-upgrade.md`](../pipeline/tts/tts-production-upgrade.md)).
6. **Auto-update on every platform**, using each platform's native update channel where one
   exists.

### Non-goals

- **Cloud rendering is never required.** An optional, explicitly opt-in cloud quality tier may
  exist later; the product must fully function offline on every platform, always (per
  `product-vision-v2.md` pillar 5).
- **Feature parity on phones for the full production pipeline is not a day-one goal.** Phones
  get defined, honest capability tiers (§2) — listening, reviewing, light patching, and pairing
  with a desktop first; on-device extraction and TTS are a later, hardware-gated stretch tier.
- **Rewriting the core engine in Rust is a near-term non-goal.** Assessed in §3.3 and rejected
  for now on ROI grounds; revisited only for isolated hot paths if embedded-CPython proves
  insufficient.
- **Real-time multi-device collaborative sync is out of scope.** §7 sketches LAN sync for a
  single user's own devices; multi-writer conflict resolution across users/devices is not
  designed here.
- **Universal Linux distro coverage is not a goal.** AppImage/deb/Flatpak on a deliberately
  chosen glibc floor (§3.6) is the target; unusual distros are not a support commitment.
- **A Mac App Store / sandboxed build is not assumed by default.** Direct distribution
  (signed + notarized DMG) is the primary macOS path; store distribution is a possible later
  addition, not a Phase 1 requirement, because App Sandbox complicates subprocess-based
  dependencies more than direct distribution does.

---

## 2. Strategy overview & platform capability tiers

The mandate ("ship on five platforms, every dependency self-contained") is achievable in full
only on desktop. Mobile platforms cannot host the Python engine as it exists today (§6), so
mobile capability is defined honestly in tiers rather than promised as parity.

### 2.1 Platform tiers

| Tier | Platforms | What it is | Engine location |
|---|---|---|---|
| **D — Desktop full pipeline** | Windows, macOS, Linux | The entire pipeline (ingestion → structure → cast → attribution → direction → TTS → assembly → QA → export) runs locally, packaged as one app. | Embedded Python engine, in-process on the same machine (§3). |
| **M0 — Mobile standalone playback** | Android, iOS | Play already-rendered chapters, browse structure/cast, read evidence, fully offline. No new inference. | None — reads a synced project bundle (§7). |
| **M1 — Mobile companion (LAN)** | Android, iOS | M0 plus: request a patch (text edit, voice reassignment, re-render), see live job progress, browse full evidence — all executed by discovering and talking to a desktop Echodraft instance over the LAN. | Desktop, over LAN (§6). |
| **M2 — Mobile on-device (stretch, flagship only)** | Android, iOS (high-end devices) | M1 plus: single-segment TTS re-synthesis and lightweight review assistance computed on-device, without the desktop reachable. Explicitly **not** the full extraction/casting/assembly pipeline. | On-device, subset engine (§6), gated by hardware tier (§9, Tier 3). |

M1 (companion mode) is the recommended default posture for mobile, not on-device standalone
inference — see §6 for the evaluation. A phone with no paired desktop and no flagship
on-device tier still gets full value from M0: it is a genuinely useful, fully offline
audiobook player and reviewer for anything already rendered.

### 2.2 Capability matrix (pipeline stage × platform tier)

| Pipeline stage | Tier D (Desktop) | Tier M1 (Mobile, companion/LAN) | Tier M0 (Mobile, standalone) | Tier M2 (Mobile, on-device stretch) |
|---|---|---|---|---|
| Ingestion (import + OCR) | Full | Trigger only (runs on paired desktop) | — | — |
| Structure extraction | Full | View progress/results only | View results only (if synced) | — |
| Cast discovery + attribution | Full | View + request re-attribution | View results only | — |
| Automatic voice casting | Full | View + reassign voice (relayed to desktop) | View only | — |
| Direction inference | Full | View only | View only | — |
| TTS rendering | Full, all engines/tiers | Trigger single-segment re-render (executes on desktop) | — | Single-segment re-synthesis, on-device |
| Assembly + mastering | Full | Trigger re-stitch (executes on desktop) | — | — |
| QA | Full | View scorecards/issues | View scorecards/issues (if synced) | — |
| Review/patch — text edit | Full | Full (request relayed to desktop) | — | — |
| Review/patch — voice/direction | Full | Full (request relayed to desktop) | — | — |
| Playback | Full | Full, online or offline once synced | Full, offline | Full, offline |
| Export (WAV/MP3/M4B) | Full | Trigger only (file lands on desktop) | — | — |

"—" means the tier does not attempt the capability at all — it is not a degraded version, it
is simply not offered, and the UI must say so rather than presenting a broken control.

---

## 3. Desktop packaging (Phase 1)

### 3.1 Shell: Tauri vs Electron

| | Electron | Tauri |
|---|---|---|
| Runtime bundled | Full Chromium + Node per app | OS-native webview (WebView2/WKWebView/WebKitGTK) + a small Rust host |
| Typical installed size | ~120–200 MB baseline before app code | ~3–10 MB installer, ~30–50 MB installed |
| Idle memory | Higher (own Chromium process tree) | Lower (shares the OS webview) |
| Sidecar/process spawning | Node `child_process`, mature ecosystem | First-class: `externalBin` in `tauri.conf.json` + `tauri-plugin-shell`, built to run exactly this "spawn a local backend and talk to it" shape |
| Auto-update | Third-party (`electron-updater`) or store channel | Built-in `tauri-plugin-updater` (signed manifests) or store channel |
| Maturity for this use case | Very mature, huge prior art in creative/desktop tools | Mature on desktop (v2), less proven on mobile |

**Recommendation: Tauri.** Justification, specific to this codebase:

- Echodraft's business logic already lives entirely in the Python FastAPI engine, not in a
  Node/Electron main process — there is nothing for Electron's Node integration to buy that a
  thin Rust host calling a local HTTP API doesn't already cover.
- The product is already sized to download multiple gigabytes of models (§5); an extra
  100–150 MB of Chromium+Node per install compounds an already-heavy footprint for no
  functional benefit. Tauri's minimal shell keeps the "self-contained app" promise from being
  undercut by the shell itself.
- Tauri's sidecar model (`externalBin`) is designed for exactly the "bundle a native backend
  executable, spawn it, talk to it over localhost" pattern this document specifies in §3.3–3.5.
- Local-first, privacy-first products benefit from Tauri's smaller attack surface (no bundled
  Node runtime with full OS access sitting in the same process as the renderer).

**Caveat:** Tauri v2 added Android/iOS targets, but they are materially newer and less
battle-tested than Tauri's desktop story. §6 recommends *not* betting the mobile shell on
Tauri today — the mobile engine story is different in kind (§6), and React Native/Expo is
recommended for mobile independent of the desktop shell choice.

### 3.2 Hosting the Next.js app: static export vs embedded server

The current frontend is already, in effect, a single-page client app (per the shared research:
one real route, one 553-line client component, no server components or server actions in use).
Given that shape, **static export (`next build` with `output: 'export'`) is the correct
choice**, not an embedded Node server:

- No Node runtime needs to run inside the shell at all — Tauri serves the pre-built
  HTML/CSS/JS directly via its asset protocol. This removes an entire process class (no
  second sidecar to spawn, heath-check, and shut down beyond the Python engine).
- It matches the existing data-flow: the UI already talks to FastAPI over HTTP for everything;
  static export changes *where the HTML/JS came from*, not how the app gets its data.
- It keeps dev and packaged builds structurally identical: in dev, `npm run dev` serves the
  same client bundle against a locally-running FastAPI on `127.0.0.1:8000`; in the packaged
  app, the same static bundle talks to the sidecar-spawned FastAPI on its negotiated port.

**Constraint this places on [`frontend-architecture.md`](../ui/frontend-architecture.md):**
the planned move to "real routes" must keep routing client-side (each route pre-rendered as a
static shell, data fetched client-side against the engine API) — Next.js server components,
server actions, and dynamic API routes are incompatible with static export and must not be
introduced as the frontend re-architecture proceeds.

### 3.3 Shipping the Python engine

Three options, assessed honestly:

**(a) PyInstaller / Briefcase-frozen sidecar binary.** Freezes the interpreter and all
dependencies into a single executable (or `--onedir` bundle) per OS/arch.

- Pros: one artifact, drops directly into Tauri's `externalBin` sidecar slot, no separate
  Python runtime concept for the shell to know about.
- Cons: heavy native dependencies the engine already has or will need — `numpy`, `onnxruntime`,
  `llama-cpp-python`, audio libraries — are a recurring source of PyInstaller import-hook
  breakage (hidden imports, missing dynamic libs); resulting binaries are large (order
  150–400 MB once onnxruntime and numpy are in); must be built natively per OS/arch (no
  meaningful cross-compilation), which pushes CI complexity into §8's build matrix regardless.

**(b) Embedded CPython (python-build-standalone) managed by the shell.** Ship a relocatable
standalone CPython build (e.g. the `indygreg/python-build-standalone` distributions) plus a
vendored `site-packages` directory built with the project's existing `uv`/lockfile workflow
(`uv pip install --target <dir>` against the pinned lockfile), invoked by the shell as
`<bundled-python> -m echodraft_api.server`.

- Pros: keeps using the exact dependency resolution the project already relies on (`uv run
  pytest` etc. stay the dev-time contract per `CLAUDE.md`); avoids PyInstaller's static-analysis
  fragility for `numpy`/`onnxruntime`/`llama-cpp-python` because packages are installed
  normally, not frozen; supports incremental updates by swapping the `site-packages` directory
  without touching the signed launcher binary (relevant to §8's versioning independence goal).
- Cons: still needs per-OS/arch wheel resolution (no cross-compiling wheels either); more
  manual plumbing than a single frozen executable — the shell must construct `sys.path` and
  manage the standalone interpreter's location itself.

**(c) Rewrite the core engine in Rust, long-term.** Assessed honestly and rejected as a
near-term goal:

- The engine's real value — text/LLM orchestration, numpy-based audio DSP in `assembly.py`/
  `mastering.py`, mature Python ML bindings (`onnxruntime`, `llama-cpp-python`), `SQLAlchemy`/
  `Alembic` for the data layer — has no equivalently mature Rust equivalent today (Rust audio/ML
  crates like `candle`/`symphonia` are real but far less battle-tested for this specific
  workload). A full rewrite is a multi-quarter effort with a highly uncertain accuracy/behavior
  parity bar (structure parsing, cast discovery, and attribution heuristics in
  `structure_parsing.py`/`cast_discovery.py`/`speaker_attribution.py` encode a lot of subtle,
  tested behavior).
- **Verdict: non-goal near-term.** If embedded-CPython startup time or footprint later proves
  to be an unfixable, user-facing problem, prefer incremental Rust for isolated hot paths
  (audio assembly/mastering DSP is the most plausible first candidate — self-contained,
  numpy-heavy, callable from Python via `PyO3`) over a full engine rewrite.

**Recommendation: (b) embedded CPython (python-build-standalone), with (a) PyInstaller onedir
as a pragmatic fallback** if standalone-interpreter plumbing takes longer to get right than a
first shippable Phase 1 milestone allows. (b) is preferred long-term because it preserves the
project's existing dependency workflow and gives a clean incremental-update story (§8); (a)
is an acceptable stopgap that ships something real while (b) is finished, not a permanent
fork of the packaging strategy.

Either option requires a **new production entrypoint**: today's dev entrypoint
(`uvicorn.run("echodraft_api.main:app", host="127.0.0.1", port=8000, reload=True)` in
`apps/api/src/echodraft_api/main.py`) hardcodes host/port and enables `reload=True`, which is
wrong for a packaged sidecar. A packaged build needs a small `echodraft_api.server` entrypoint
that accepts host/port/bind-token via CLI args or environment variables, binds to an
OS-assigned ephemeral port (`port=0`) by default, disables reload, and performs the port/token
handoff described in §3.4.

### 3.4 Sidecar lifecycle

1. **Spawn.** On launch, the Tauri host resolves the bundled interpreter and vendored app code
   for the current OS/arch and spawns it via the shell plugin's sidecar API:
   `<bundled-python> -m echodraft_api.server --host 127.0.0.1 --port 0 --token <generated>`.
   Port `0` asks the OS for a free ephemeral port, avoiding collisions with anything else on the
   machine (including a previous crashed instance still shutting down).
2. **Port negotiation.** Immediately after binding, the engine writes its actual port and a
   freshly generated bearer token to a small JSON file in an app-local runtime directory (e.g.
   `.echodraft/runtime/engine.json`, restrictive file permissions). The Tauri host polls for
   this file (bounded retries, short interval) rather than parsing subprocess stdout, so the
   mechanism keeps working even if log formatting changes.
3. **Health check.** The host polls `GET /api/v1/healthz` with the bearer token until it returns
   `200 OK`, with a bounded timeout (e.g. ~15 s) and backoff. The UI shows an explicit "Starting
   engine" state bound to this phase — never a blank or frozen window while the engine boots.
4. **Crash restart.** The host supervises the child process. On an unexpected non-zero exit, it
   restarts up to a small retry budget with backoff, and — critically — surfaces a persistent
   "Engine restarted after a crash" notice rather than restarting silently. Silent auto-recovery
   would hide real bugs from users and from the team; that is inconsistent with this project's
   "truthful capability claims only" stance. The last N lines of the crash are captured to a
   rotated crash-report file alongside the regular logs.
5. **Logs.** The engine already emits structured logs (`echodraft_api/logging.py`,
   per [`architecture.md`](../architecture/architecture.md)'s "structured logs from day one").
   The sidecar wrapper redirects stdout/stderr to a rotating file under the app-local data
   directory (e.g. `.echodraft/logs/engine.log`, size-capped with rotation) so nothing depends
   on an attached terminal, and an "Open logs folder" action (settings/about screen) exposes
   them for support without requiring a technical user to find `.echodraft` themselves.
6. **Clean shutdown.** On app quit, the host requests a graceful shutdown (an authenticated
   `POST /api/v1/shutdown`, or a SIGTERM/CTRL_BREAK equivalent to the child process) and waits a
   bounded timeout (e.g. 5 s) before force-killing. This matters concretely: SQLite is opened in
   WAL mode with a 30 s busy timeout today, and the `InProcessJobRunner`'s
   `ThreadPoolExecutor(max_workers=2)` (`jobs.py`) may have in-flight work. On shutdown request,
   the engine should refuse new job starts and let running jobs reach their next checkpoint
   (this ties directly to the resumable-DAG checkpointing designed in
   [`target-architecture.md`](../architecture/target-architecture.md) — a forced kill mid-job
   must be *resumable*, not merely non-corrupting).

### 3.5 IPC: localhost HTTP + auth token

All UI↔engine traffic stays plain HTTP(S) on `127.0.0.1` at the negotiated port, with the
bearer token from §3.4 required on every request (`Authorization: Bearer <token>`); requests
missing or presenting a stale token get `401`. This is a genuine improvement over today's dev
setup, where `127.0.0.1:8000` accepts requests from any local process with no authentication
at all — packaging is the natural point to close that gap, since the token now has somewhere
principled to live (the runtime handoff file, generated fresh per process launch, never
persisted beyond it). Event push for live progress (per `target-architecture.md`'s
event-push design, replacing today's five recursive polling loops) rides the same
authenticated localhost connection (SSE or WebSocket) rather than a separate channel.

### 3.6 Per-OS packaging specifics

**macOS.** Code signing with a Developer ID certificate plus notarization (`notarytool`) is
mandatory for Gatekeeper to allow the app to launch without a manual override. Every Mach-O
binary inside the bundle needs a valid signature, not just the top-level app — this includes
the bundled Python interpreter, any `.dylib`s pulled in by `onnxruntime`/`llama-cpp-python`,
and the FFmpeg binary from §4; unsigned nested binaries are a common cause of notarization
rejection. Build for Apple Silicon (arm64) as the primary target, matching today's "practical
on a single Apple Silicon machine" baseline (`architecture.md`), while deciding deliberately
whether to also ship an Intel (x86_64) or `universal2` build rather than silently dropping
Intel support. The CoreML execution provider for `onnxruntime` (§4, §9) is macOS/iOS-only and
is the natural GPU/NPU path on this platform.

**Windows.** Two viable distribution shapes: MSIX (Store-compatible, sandboxed, auto-updates
via the Store or App Installer) or a traditional NSIS/WiX-built signed EXE for direct
distribution. Either way, an Authenticode code-signing certificate is required to avoid
SmartScreen warnings on first run. Tauri's Windows target depends on the WebView2 runtime;
modern Windows 10/11 ship it, but the installer should still bootstrap it for older systems
rather than assuming its presence. Once bundling replaces system-tool discovery, the
winget-path-guessing logic in `system_tools.py` becomes dead code for the packaged app and
should be retired (kept only as a short-lived escape hatch during the migration in §10, if
at all). The DirectML execution provider is the pragmatic GPU path here — it works on any
DX12 GPU without vendor lock-in to CUDA, matching this project's "no GPU path today, but no
gratuitous vendor lock-in either" posture.

**Linux.** No single dominant packaging format, so ship three: an **AppImage** (works
anywhere, no install or root required — closest to the "just download and run" simplicity of
the other platforms), a **`.deb`** for Debian/Ubuntu users who expect proper package
management, and a **Flatpak** (via Flathub) for sandboxed distribution. The glibc floor must
be chosen deliberately (build in an old-enough container image) since even AppImage still
links against the host's glibc. Flatpak's sandbox complicates the subprocess-spawning and
filesystem-access patterns this app relies on (spawning bundled FFmpeg/llama.cpp binaries,
writing large model files) and needs `xdg-desktop-portal` integration for file access — this
needs real engineering budget, not a same-day afterthought bolted onto the other two formats.

---

## 4. Self-contained dependency plan

Every dependency the engine shells out to today must become something the app bundles or
downloads itself — no PATH lookups, no assumption of a system package manager. This table
replaces every row in today's `model_catalog.yaml` that has `install_type: system_tool`.

| Dependency | Today | Replacement | Approx. size | License | Per-OS notes |
|---|---|---|---|---|---|
| **Poppler** (`pdftoppm`, PDF page rendering for OCR) | System binary via Homebrew/winget/apt (`model_catalog.yaml`: "GPL-compatible... verify distribution obligations") | **pypdfium2** — Python binding to Google's PDFium (the same renderer Chrome uses) | ~15–25 MB per-platform wheel | BSD-3-Clause / Apache-2.0 (PDFium) — clean, dual-permissive | Prebuilt wheels exist for Windows/macOS/Linux, x86_64 and arm64; no compiler or system install needed at all. Also resolves the GPL-obligation question flagged in the current catalog. |
| **Tesseract** (baseline OCR) | System binary via Homebrew/winget/apt; Windows lookup is a fragile winget-install-path guess (`system_tools.py`) | **RapidOCR** (ONNX-based PP-OCR det/rec/cls models on `onnxruntime`) as the new default; a bundled static Tesseract binary + `eng.traineddata` retained as a fallback/compat path during transition | RapidOCR: ~15–45 MB of ONNX models; Tesseract fallback: ~15 MB binary + ~15 MB/language | RapidOCR: Apache-2.0; Tesseract: Apache-2.0 | RapidOCR needs no external binary at all — it runs through the same `onnxruntime` the TTS/LLM stack already depends on, and removes the per-OS binary-path guessing entirely. Keep both behind one OCR provider contract so relative accuracy can be evaluated before fully retiring Tesseract. |
| **FFmpeg** (resample, mastering `loudnorm`, MP3/M4B mux) | System binary via Homebrew/winget/apt (`model_catalog.yaml`: "LGPL/GPL build dependent; verify codec distribution obligations") | Bundle a **static, LGPL-only build** per OS/arch (configured `--disable-gpl --enable-lgpl`, no `libx264`/`libx265`) | ~30–70 MB per platform | LGPL-2.1+ if the build genuinely excludes GPL codecs — **must be audited**, not assumed | The pipeline only needs PCM/AAC/MP3 encode + the `loudnorm` filter — no GPL codec is actually required, so an LGPL-only build is realistic. Keep FFmpeg as a bundled *subprocess*, matching `mastering.py`/`assembly.py`'s existing calling convention almost unchanged, rather than switching to PyAV (which bundles the same libav code and does not remove the licensing question, only relocates it). |
| **Ollama** (external LLM runtime + `ollama pull`) | System runtime via Homebrew/apt/winget; blocking `urllib.request` HTTP calls to `127.0.0.1:11434` (`local_llm.py`) | **`llama-cpp-python`** (in-process, preferred) or a bundled **`llama-server`** sidecar (fallback where an in-process GPU wheel isn't available) | Runtime: ~5–50 MB depending on CPU/CUDA/Metal build variant; GGUF weights: ~2.5–5 GB for a 4B-class quant | llama.cpp runtime: MIT; model license varies (unchanged from today's Qwen3 consent requirement) | In-process `llama-cpp-python` removes a whole sidecar and its HTTP hop — `local_llm.py`'s blocking-call structure becomes a direct function call. GGUF models are downloaded by the app's own download manager (§5), never via `ollama pull`. |
| **whisper.cpp CLI** (`whisper-cli`, optional ASR word-match QA) | Optional system binary on PATH, gated by `ECHODRAFT_ASR_EXECUTABLE`/`ECHODRAFT_ASR_MODEL_PATH` | Bundle the whisper.cpp library or its Python binding (e.g. `pywhispercpp`) directly | ~5–20 MB runtime + ~75–150 MB for a tiny/base ggml model | MIT (runtime); ASR model license per upstream release | Same contract as today in `asr_verification.py` — only the "must be on PATH" assumption goes away. |
| **Kokoro 82M ONNX** (default TTS) | "Managed" today via `kokoro_setup.py`: creates a throwaway venv, `pip install kokoro-onnx==0.4.7`, downloads model + voices with a bare `urllib.request` call and **no checksum verification** | Keep ONNX weights + `onnxruntime` inference (the right shape already); drop the nested venv/pip-install step and vendor the inference code + `onnxruntime` into the shipped engine's own environment; **add sha256 verification** to the model/voice downloads | ~350 MB total (unchanged) | Model + package licenses are third-party (existing consent language stays) | Removes a real reliability gap: today's `_download()` in `kokoro_setup.py` accepts any non-empty file with no integrity check — a truncated or corrupted download currently fails later, silently, at synthesis time. |
| **onnxruntime execution providers** (GPU/NPU acceleration) | None — "no GPU path anywhere" today | Bundle CPU `onnxruntime` as the universal floor; add **CUDA** (Windows/Linux + NVIDIA), **DirectML** (Windows, any DX12 GPU), **CoreML** (macOS/iOS, Apple Silicon), **NNAPI** (Android) as optional downloads | 100–700 MB per provider | Apache-2.0 (onnxruntime); provider SDKs typically permissive/vendor-redistributable | These are additive, hardware-gated downloads (§5, §9), never part of the minimal core install. |

---

## 5. Model & asset download manager v2

This is the direct evolution of Model Center (`apps/api/src/echodraft_api/local_ai/service.py`,
`model_catalog.yaml`, `ModelInstallationRecord`/`ModelInstallJobRecord`). The consent-flag
pattern, the job-runner-backed install flow, and the health/verification split (runtime check
vs. persisted installation record) all carry forward unchanged in spirit — what changes is that
every catalog entry now describes *bundled or downloadable artifacts per platform*, not a
system package manager identifier.

**Manifest-driven catalog with per-platform artifacts.** Extend the `model_catalog.yaml` shape
so an entry can declare one artifact per OS/arch/accelerator combination instead of a single
`packages: {homebrew, apt, winget}` block:

```yaml
models:
  llama_cpp_runtime:
    display_name: llama.cpp Runtime
    capability: local_llm_runtime
    provider: llama_cpp
    install_type: bundled_runtime
    required: true
    license_summary: MIT
    artifacts:
      windows-x64-cpu:   { url: "...", sha256: "...", size_mb: 40 }
      windows-x64-cuda:  { url: "...", sha256: "...", size_mb: 180 }
      macos-arm64:       { url: "...", sha256: "...", size_mb: 35 }
      linux-x64-cpu:     { url: "...", sha256: "...", size_mb: 45 }
```

**Resumable, verified downloads.** Replace `kokoro_setup.py`'s single-shot
`urlopen`/`copyfileobj` with a downloader that (1) issues `Range` requests to resume a `.part`
file after any interruption, (2) streams through a running SHA-256 digest and compares it to
the manifest-pinned hash before an atomic rename into place, and (3) reports byte-level
progress to the same job-progress channel `kokoro_setup.py`'s `PHASES`/`_progress` mechanism
already uses — the UI pattern does not need to change, only its granularity.

**Storage budgeting and eviction.** Unify the model root into one tree
(`.echodraft/models/<capability>/<model_key>/<version>/`), let the user set a storage budget in
settings, warn before a download would exceed it, and support an eviction policy (evict
least-recently-used, unreferenced models first). A model still named by any project's render
history — including unrendered chapters awaiting that exact model version — is never
auto-evicted.

**Hardware detection → recommended bundle.** Run on first launch and on demand from settings:

1. Detect OS + architecture (already done today via `platform.system()`/`platform.machine()`
   in `system_tools.py`/`kokoro_setup.py`).
2. Detect RAM and CPU core/AVX2 support — informs whether a Q4 vs. Q8 GGUF quant, or a
   CPU-only `onnxruntime` path, is realistic.
3. Detect a discrete GPU and VRAM: NVIDIA via `pynvml`/`nvidia-smi` on Windows/Linux (CUDA
   path); DXGI adapter enumeration on Windows for any DX12 GPU (DirectML path); Apple Silicon
   unified memory via `sysctl`/Metal device query on macOS (CoreML path); NPU/Neural Engine
   presence on Android/iOS informs the mobile stretch tier (§6).
4. Map the `(RAM, VRAM, cores, OS)` tuple to one of the hardware tiers in §9 and pre-select a
   recommended bundle (e.g. CPU-only laptop → Kokoro ONNX CPU + a 4B-class Q4 GGUF on CPU;
   GPU desktop → the same TTS engine GPU-accelerated + a larger quant + CUDA/DirectML).
5. The user can always override the recommendation — the probe sets a sensible default, never
   a hard gate.

**First-run experience.** The app downloads only a **minimal core bundle** on first launch:
the embedded engine, one small default LLM quant, Kokoro ONNX (CPU), and pypdfium2/RapidOCR —
enough to take a plain-text or EPUB book through the entire pipeline end-to-end. (For scale:
today's *required* catalog entries alone — Ollama runtime, `qwen3:4b`, Kokoro — already total
roughly 3.85 GB by their own `size_mb` estimates; the v2 minimal core should land measurably
below that by making the LLM runtime itself tiny and letting model weights be the only large
line item.) Every optional model — additional OCR languages, alternate TTS engines/voices,
larger LLM quants, GPU execution providers — downloads on demand the first time a feature
needs it, behind the existing consent-flag pattern: explicit confirmation for network use,
license shown, size shown, before the user confirms. This is an extension of Model Center's
existing install-confirmation flow, not a new pattern.

**Offline behavior.** Once the minimal core (plus anything else installed) is present, the
pipeline runs with zero network access. The manager must distinguish "not installed" from
"installed, network currently unavailable" — a working offline install must never be blocked
on re-verifying a hash that already matched at install time. Attempting to install something
new while offline fails immediately with an actionable message, matching Model Center's
existing "fail with actionable errors instead of silently falling back" stance for unsupported
platforms.

**Delta/update strategy for models.** Each model lives in a versioned directory; an update
downloads the new version alongside the old one, verifies it, and only then flips an "active"
pointer — an interrupted update never corrupts a working install, and a render already made
against the previous version stays reproducible because its `render_identity` pinned that
version at render time (per `tts-production-upgrade.md`'s existing fingerprint fields). Old
versions become eviction candidates once no unexported render history references them.

---

## 6. Mobile (Phase 2)

### Shell options

| Option | Description | Trade-off |
|---|---|---|
| **(a) Capacitor over the existing web UI** | Wrap the static-exported Next.js UI in Capacitor's native shell | Maximum reuse with desktop/web; fastest to a first build; WebView-based UI can feel less native for scrolling/gestures; background-audio and foreground-service support still need native plugin glue regardless |
| **(b) React Native/Expo sharing the design system** | A genuinely native UI built against the same design tokens (`design-system.md`) but a separate component implementation | Better scrolling/gestures/platform feel; first-class background-audio and lock-screen controls via Expo AV; a second UI codebase to maintain alongside the web app |
| **(c) Fully native shells (SwiftUI + Jetpack Compose)** | Two platform-native codebases | Best possible integration; highest engineering cost; not justified until mobile's narrower scope is proven to need it |

**Recommendation: (b) React Native/Expo**, sharing the design system's *tokens*, not its React
web component implementation. Mobile's actual job — per the honest tiers in §2 — is playback,
light review/patch, and companion pairing, not hosting the full editing surface; a genuinely
native-feeling player and reviewer matters more here than maximizing code-sharing with the
desktop web bundle, and Expo's audio/background/notification APIs directly serve "listen
offline, patch light, pair with desktop." Treat (a) Capacitor as the fallback if engineering
capacity requires a faster, thinner first mobile release closer to a reskinned companion web
view.

### Mobile engine strategy

The Python sidecar from §3 **cannot** ship on mobile: iOS's App Sandbox forbids spawning
arbitrary subprocesses, and Android aggressively restricts long-lived background native
processes outside a foreground service. Two strategies, in priority order:

**Companion mode (primary, Phase 2 default).** The phone runs no pipeline at all. It
discovers a paired desktop Echodraft instance on the LAN via mDNS/Bonjour
(`_echodraft._tcp.local.`), pairs once (a QR code or short numeric code shown on the desktop,
exchanged over the LAN to mint a long-lived device token — the same bearer-token pattern as
the desktop sidecar's localhost auth in §3.5, scoped to the LAN instead of loopback), and then
talks to the desktop's existing FastAPI/event-push API exactly as the desktop UI does. Already
rendered chapters sync for offline playback (§7); anything requiring new inference (a
patched-segment re-render) needs the desktop reachable.

**On-device stretch tier (flagship devices only, opt-in, later in Phase 2).** A much smaller
subset engine embedded directly in the mobile app: ONNX Runtime Mobile (or CoreML on iOS)
running the same Kokoro-class TTS model for local re-synthesis of a single edited segment
without the desktop online, and optionally a small quantized GGUF model via a mobile
llama.cpp binding for lightweight review assistance (e.g. re-summarizing a flagged
attribution) — explicitly **not** the full extraction/casting/assembly pipeline, gated behind
the flagship-phone hardware check in §9 (Tier 3).

Full pipeline parity on mobile is a deliberate non-goal for Phase 2, matching the mandate's own
framing: feature parity on phones for the full production pipeline is not required day one.

### iOS constraints

- **No arbitrary subprocess execution.** App Sandbox rules out shipping FFmpeg/llama.cpp/OCR
  as spawned external binaries the way desktop does; every native dependency must be a linked
  framework called in-process (e.g. `onnxruntime` as a static/dynamic framework), never a CLI.
- **Background audio** requires declaring the `audio` background mode and driving playback
  through `AVAudioSession`/`AVPlayer` correctly — needed for the playback job, irrelevant to
  rendering, which does not run in the background on iOS.
- **On-demand resources / post-install downloads.** Large model weights must not be bundled in
  the initial `.ipa` (App Store size-consciousness, cellular download limits); they download
  after install, same pattern as desktop's first-run flow (§5). Apple's review treats
  downloaded **model weights as data** — fine — but a downloaded native **executable** fetched
  at runtime is not permitted under App Store review guidelines. This is a hard constraint: the
  on-device stretch tier's inference runtime must be compiled into the signed app binary itself
  (a linked framework); only model weights are ever downloaded separately.

### Android constraints

- **Foreground services for long work.** The on-device stretch tier's TTS re-synthesis must run
  in a foreground service with a persistent notification (Android kills background work
  aggressively otherwise; Android 14+ requires declaring the foreground service type, e.g.
  `mediaProcessing`).
- **Scoped storage / Storage Access Framework** governs where large model files can be written
  — no assumption of legacy broad filesystem access.
- **ABI splits.** `arm64-v8a` is the primary target; `armeabi-v7a` is likely droppable;
  `x86_64` matters for emulators/Chromebooks. Each ABI needs its own `onnxruntime`/llama.cpp
  native library variant, which feeds directly into the download manager's per-platform-artifact
  model from §5.

**Playback and review are fully offline on both platforms**, once chapters are synced or
rendered, regardless of tier. This is the one mobile capability that must never depend on LAN
or cloud reachability — it is the local-first constraint applied to the phone.

---

## 7. Data & sync

**Project portability.** A project is already, by design, an artifact tree on the filesystem
plus SQLite metadata (per `architecture.md`'s storage layout) — inherently portable. Formalize
this as an explicit **project bundle** export/import feature rather than relying on users to
copy `.echodraft` directories by hand: a bundle is an archive containing a
`bundle_manifest.json` (schema version, project id, exported-at timestamp, included artifact
paths + hashes), the relevant SQLite rows (or the whole SQLite file, since it is
single-file), and the artifact tree.

**Export/import between devices.** The bundle is the mechanism for "move this project from my
desktop to my laptop" or "hand this project to a collaborator," with no server involved.
Import validates the bundle's schema version against the running app's schema — mismatches are
rejected or offered a migration path, never silently imported — then extracts artifacts and
merges/creates DB rows inside a transaction, so a failed import cannot leave partial state.

**LAN sync sketch (later phase; no cloud requirement).** Builds directly on companion-mode
pairing (§6): once a phone is paired with a desktop instance, a background job opportunistically
copies newly rendered chapter artifacts and manifest deltas to the phone (on Wi-Fi, or
on-demand "sync now"), using the same content-addressed render paths already in place
(`audio/segments/{segment_id}/{render_key}/{render_id}/...`) so sync is naturally resumable and
de-duplicated — a render that already exists locally by hash is skipped. Conflicts are
structurally rare because the phone in companion mode is a read-mostly consumer: patch requests
round-trip through the desktop engine, which remains the single source of truth for append-only
render history, rather than the phone independently writing history. True multi-writer sync
(e.g. two desktops) is out of scope until there is a demonstrated need.

---

## 8. Update & release engineering

**App auto-update per platform.** Tauri's built-in updater (signed update manifests, checked
on launch or on a schedule, user-confirmed install-and-restart) covers Windows/Linux
direct-distribution builds. Native store channels apply where used: Microsoft Store
auto-update for an MSIX build, Flathub's normal channel for the Flatpak, and the AppImage's own
update mechanism (or re-download) for that format. A macOS Store build (if ever pursued) would
use Mac App Store auto-update; the recommended direct-distribution DMG uses the Tauri updater
the same as Windows/Linux.

**Engine/model versioning independence.** An app shell update must never silently invalidate
existing render history. The mechanism already exists in embryonic form: segment render
fingerprints already include "active TTS provider identity and model version"
([`tts-production-upgrade.md`](../pipeline/tts/tts-production-upgrade.md)), and the invalidation
rules in `architecture.md` key staleness off explicit content/config changes, never off "the app
got updated." Build on this with three independent version numbers — shell/UI version, engine
version, and per-model version:

1. A packaging-only shell update must never bump a model's effective `render_identity` value —
   only an actual model-weights or engine-behavior change may do that.
2. Old engine/model versions stay installable side by side during a transition window, so a
   shell update never forces a user to re-render an in-progress book to keep working.
3. This mirrors §5's "download alongside, then flip the active pointer" model-update strategy —
   the same discipline applies to the engine itself, not just to models.

**CI build matrix.** Per-OS/arch jobs (windows-x64, macos-arm64, macos-x64 or universal2,
linux-x64) each produce: the Tauri shell bundle, the embedded-CPython + vendored `site-packages`
sidecar, and the OS-specific installer (MSIX/NSIS, notarized DMG, AppImage/deb/Flatpak). A
separate mobile matrix (Android AAB/APK per ABI; iOS IPA via a macOS runner) starts once Phase 2
begins. Signing secrets (Apple Developer ID + notarization credentials, an Authenticode
certificate, an Android keystore) live only in CI secrets, never in the repository. Release
builds are gated on the existing verification suite from `CLAUDE.md` passing first: `uv run
pytest`, `uv run ruff check .`, `uv run mypy ...`, `npm run web:lint`, `npm run
web:typecheck`, `npm run web:test:smoke`.

---

## 9. Hardware tiers

These tiers are the vocabulary [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)
should consume for its own engine-tiering-per-hardware section, rather than redefining hardware
classes independently. Wall-clock figures marked "target" are engineering targets carried
forward from `product-vision-v2.md` §5.1's speed goals, not measurements; they must be validated
empirically once the parallel-DAG work in `target-architecture.md` lands, and updated here once
real numbers exist.

| Tier | Hardware profile | TTS engine | LLM | Understanding phase (500-page target) | Full render (500-page target) | Platform |
|---|---|---|---|---|---|---|
| **1 — CPU-only laptop** | 8–16 GB RAM, no discrete GPU, modern x86_64 or Apple Silicon CPU | Kokoro ONNX, CPU execution provider (today's default) | ~4B-class, Q4 GGUF, CPU | ≤ 30–45 min (mid-tier target, `product-vision-v2` §5.1) | Roughly 1–3 h with segment-level parallel rendering across cores (vs. today's fully sequential single-worker-lock rendering) | Desktop |
| **2 — GPU desktop** | 16–32 GB+ RAM, discrete NVIDIA (CUDA), any modern DX12 GPU (DirectML), or Apple Silicon (CoreML/Metal), 6 GB+ VRAM | Kokoro ONNX GPU-accelerated; optional higher-fidelity engine (e.g. XTTS-v2 with GPU actually enabled, closing today's hardcoded `gpu=False` gap) | 8B–14B-class quant, GPU-resident | ≤ 15 min (GPU-class target, `product-vision-v2` §5.1) | Well under an hour with GPU-accelerated parallel TTS | Desktop |
| **3 — Flagship phone** | Current-gen flagship, 8 GB+ RAM, on-device NPU/Neural Engine | On-device stretch tier only: ONNX Runtime Mobile/CoreML, single-segment re-synthesis | 1–3B-class quant, on-device, review-assist only | N/A — full pipeline not attempted on-device | N/A — single-segment re-render only | Mobile (M2, opt-in) |
| **4 — Older/budget phone** | < 6 GB RAM, no NPU | None on-device | None on-device | N/A | N/A | Mobile (M0/M1 — companion + offline playback only) |

Tiers 3 and 4 both default to companion mode (§6) regardless of on-device capability — Tier 3's
on-device stretch tier is an *addition* to companion mode, not a replacement for it.

---

## 10. Phasing & migration path; risks & open questions

### Phasing

- **Stage 0 (today).** Developer runs `uv run` + `npm run dev`; poppler/tesseract/ffmpeg/Ollama
  are installed manually via Homebrew/winget/apt; no packaging exists.
- **Stage 1 — dependency self-containment inside the current dev workflow.** Replace every
  system-tool call site with its bundled equivalent from §4 (pypdfium2, RapidOCR,
  bundled FFmpeg, `llama-cpp-python`, bundled whisper.cpp) while still running via `uv run` /
  `npm run dev`. This validates each replacement in isolation, without simultaneously debugging
  a new shell. Model Center evolves into the v2 download manager (§5) during this stage.
- **Stage 2 — first desktop shell.** Wrap the now-self-contained engine plus the
  static-exported UI in Tauri for one OS (macOS first, matching today's "practical on a single
  Apple Silicon machine" baseline) as a smoke test of the full sidecar lifecycle (§3.4).
- **Stage 3 — full desktop matrix.** Windows/macOS/Linux, signed and notarized installers,
  auto-update wired up (§8). This is Phase D from `product-vision-v2.md`.
- **Stage 4 — mobile companion mode.** Android and iOS ship the M0/M1 tiers (§2, §6) — the
  first slice of Phase E.
- **Stage 5 (stretch, opt-in) — mobile on-device tier.** The M2 tier (§6, §9 Tier 3) for
  flagship devices, gated on Stage 4 being stable and on validating real on-device model
  size/performance rather than committing to it on paper.

### Risks & open questions

- **Licensing table gaps.** The FFmpeg LGPL-only build must be audited to confirm no GPL codec
  slipped in; Poppler's licensing question in `model_catalog.yaml` disappears once pypdfium2
  replaces it, but every other bundled binary (llama.cpp, whisper.cpp, RapidOCR models, the
  Kokoro model, the Qwen3/replacement GGUF weights) needs the same audit rigor before commercial
  distribution. A single, dedicated dependency-license ledger is a real follow-up this document
  flags but does not itself produce.
- **iOS on-device LLM feasibility is unproven.** llama.cpp compiles for iOS and CoreML/Metal
  access to the Neural Engine is real, but running even a 1–3B quantized model within iOS's
  aggressive memory-pressure/jetsam limits, on top of an already-large app binary, has not been
  prototyped for this codebase. This must be validated before Stage 5 gets a committed date.
- **Binary/download sizes.** The desktop minimal core (§5) already lands near or above 1 GB
  once LLM weights are counted; mobile users are far less tolerant of multi-gigabyte first-run
  downloads even when technically permitted by store review. The on-demand-download pattern is
  mandatory, not optional, on mobile, and the "your book needs a 2 GB download before it can
  finish rendering" moment needs its own UX treatment (owned by `design-system.md` /
  `frontend-architecture.md`, not this document).
- **Tauri's mobile maturity.** This is exactly why §6 recommends React Native/Expo instead of
  extending the desktop shell choice to mobile — Tauri's Android/iOS targets are newer and less
  proven than its desktop story. Revisit only if Tauri mobile matures enough to justify
  unifying the shell.
- **Companion-mode LAN discovery reliability.** mDNS/Bonjour discovery across consumer routers
  (client isolation on some Wi-Fi access points, VPNs, guest networks) is a known source of
  "why can't my phone find my laptop" support friction. A manual-IP or QR-code fallback pairing
  path is needed from day one, not added later as a patch.
- **Pressure to revisit the Rust-rewrite non-goal.** If embedded-CPython startup time or
  install footprint becomes a real, unfixable user-facing problem post-launch, the right
  response is an isolated Rust hot path (audio assembly/mastering DSP is the most plausible
  first candidate) — not reopening a full engine rewrite, which §3.3 has already assessed as
  poor ROI given the maturity gap in Rust's ML/audio ecosystem versus Python's.
