# Target Architecture

This is the **v2 / target** system architecture for Echodraft: the complete
local-first engine that turns any rights-cleared book into an editable,
patchable, multi-voice audiobook, and that will later be embedded inside
desktop and mobile app shells.

It is the architectural counterpart to the product north-star in
[`../product/product-vision-v2.md`](../product/product-vision-v2.md). Where this
document describes *how the engine is built*, the sibling docs describe the
internals of each subsystem:

- [`extraction-pipeline-v2.md`](extraction-pipeline-v2.md) — book-understanding stage internals (structure, cast, attribution).
- [`../pipeline/casting/automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md) — automatic voice assignment.
- [`../pipeline/tts/tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md) — production TTS + emotion.
- [`../pipeline/assembly/generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md) — AI ambience/music/SFX.
- [`../ui/frontend-architecture.md`](../ui/frontend-architecture.md) — the UI shell that consumes this engine.
- [`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md) — packaging the engine per platform.

It supersedes the runtime/orchestration parts of
[`architecture.md`](architecture.md) and the "current state" analysis in
[`end-to-end-workflow-architecture.md`](end-to-end-workflow-architecture.md),
which remain valid as descriptions of the shipping code. The pipeline manifest
contract in [`pipeline-manifest-spec.md`](pipeline-manifest-spec.md) is extended
here, not replaced.

---

## 1. Purpose, goals, non-goals

### Purpose

Deliver an engine that produces a full, listenable audiobook draft from a book
with **near-zero manual resolution**, in **minutes-to-first-audio** rather than
hours-to-completion, and that runs entirely on the user's own machine across
five OS targets. The current architecture produces the right *data* (evidence,
manifests, append-only renders) but fails on three axes the product cannot
tolerate: it is **slow** (a real 500-page run took 6h57m — see
[`end-to-end-workflow-architecture.md`](end-to-end-workflow-architecture.md) §
"Last Completed Job Analysis"), **non-resumable** (an API restart marks every
`RUNNING` job `FAILED`), and **serial** (the only concurrency primitive in the
entire backend is `ThreadPoolExecutor(max_workers=2)` in
[`jobs.py`](../../apps/api/src/echodraft_api/jobs.py), used only to separate
whole jobs — there is zero intra-job concurrency).

### Goals

1. **Perceived speed first.** The user should hear finished chapter-1 audio
   while later chapters are still being extracted. Wall-clock completion matters
   less than time-to-first-audio.
2. **Resumability by construction.** Any job can be killed at any moment (crash,
   quit, OS sleep, laptop lid) and resumes mid-stage on restart with no lost
   work and no duplicated inference.
3. **Massive intra-job parallelism**, bounded per resource class so the machine
   stays responsive and the local model server is never overloaded.
4. **Near-free reruns.** Re-running a stage after a small edit recomputes only
   what changed; identical (model, prompt, input) tuples never re-infer.
5. **Engine/UI separation** as the enabler for cross-platform packaging.
6. **Push, not poll.** Progress reaches every UI shell as an event stream.
7. Preserve every hard constraint (§4 of the shared brief): segment-first,
   manifest-driven, patchable, local-first, append-only renders, no audio in the
   DB, SQLite + filesystem.

### Non-goals

- **Not** a distributed/cloud job system. The hosted evolution path in
  [`architecture.md`](architecture.md) remains additive and out of scope here;
  the target is a single-machine engine (with optional, never-mandatory cloud
  offload) — see [`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md).
- **Not** a change to the segment as the atomic unit. Fan-out adds finer *work
  units* (page, scene window, candidate) but the durable editable/renderable
  entity stays the segment.
- **Not** a rewrite of stage *algorithms* — those live in
  [`extraction-pipeline-v2.md`](extraction-pipeline-v2.md) and the pipeline
  docs. This document defines the *orchestration, runtime, storage, and API*
  they plug into.
- **Not** a general workflow engine. The DAG is book-production-shaped and
  ships in-process; we do not adopt Airflow/Temporal/Celery (they violate
  local-first, zero-manual-install, and single-binary packaging).

---

## 2. Architecture overview

### Layered target

```text
+-----------------------------------------------------------------------------+
|  UI SHELL(S)   Next.js web (dev)  ·  Tauri desktop  ·  mobile webview        |
|                (docs/ui/frontend-architecture.md)                           |
|   - renders state, never owns pipeline logic                                |
|   - subscribes to the event stream; no polling                             |
+------------------------------ HTTP + SSE/WS -------------------------------+
                                     |
                                     v   127.0.0.1 loopback only
+-----------------------------------------------------------------------------+
|  LOCAL API  (FastAPI, apps/api)                                            |
|   - thin transport: request validation, auth-to-localhost, pagination      |
|   - job control endpoints (submit / cancel / retry)                        |
|   - event stream endpoint (SSE primary, WS optional)                       |
|   - delegates ALL work to the Engine Core; owns no long loops              |
+-----------------------------------------------------------------------------+
                                     |
                                     v  (in-process function calls today;
                                         IPC boundary when embedded)
+-----------------------------------------------------------------------------+
|  ENGINE CORE                                                               |
|   +---------------------+   +-----------------------------------------+     |
|   | Pipeline Orchestr.  |   | Stage services                          |     |
|   |  - DAG scheduler    |-->|  ingestion · structure · cast · attrib. |     |
|   |  - work queue       |   |  direction · casting · render · assembly|     |
|   |  - checkpoint store  |   |  qa · export · sound-design             |     |
|   |  - event bus        |   |  (each exposes: plan() -> units,        |     |
|   |  - cache layer      |   |   run_unit(unit) -> outputs)            |     |
|   +---------------------+   +-----------------------------------------+     |
+-----------------------------------------------------------------------------+
        |                          |                         |
        v                          v                         v
+----------------+   +-------------------------+   +-------------------------+
| INFERENCE      |   |  STORAGE                |   |  SUBPROCESS / TOOLS      |
| RUNTIME        |   |  - SQLite (metadata,    |   |  - Poppler, Tesseract    |
|  - provider    |   |    checkpoints, cache,  |   |  - ffmpeg                 |
|    abstraction |   |    events, issues)      |   |  - Model Center installs |
|  - LLM workers |   |  - filesystem artifacts |   |    (docs/architecture/   |
|  - TTS workers |   |    (text, WAV, manifests)|  |     local-ai/model-center)|
|  - audio-gen   |   |  - JSON manifests        |   +-------------------------+
|  - GPU sched.  |   +-------------------------+
+----------------+
```

### Why the engine/UI split is the key enabler

Today the "product" is effectively one 553-line client component
(`app/project-dashboard.tsx`) talking to a FastAPI process that *is* the engine.
That fusion is why the app cannot ship on five platforms: a browser tab cannot
own OCR subprocesses, GPU scheduling, or a resumable job runner.

The target draws one hard line: **the Engine Core is a headless library with a
stable local API, and every UI is a replaceable client of that API.** This is
the single decision that makes cross-platform packaging tractable, because it
lets each platform pick a shell without touching pipeline code:

| Platform | Shell | Engine placement |
|---|---|---|
| Windows / macOS / Linux | Tauri (system webview) | engine as bundled sidecar binary |
| iOS / Android | native webview | engine as embedded service or on-device server |
| Dev / web | Next.js | engine as local FastAPI process |

The contract is identical everywhere: **HTTP for request/response, SSE (or
WebSocket) for the event stream, loopback-only.** See
[`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
for packaging, dependency download, and hardware tiering; see
[`../ui/frontend-architecture.md`](../ui/frontend-architecture.md) for the client
side of this contract.

The engine must therefore hold **zero UI assumptions**: no coupling to a
specific frontend, no server-rendered HTML, all state reconstructable from
SQLite + filesystem so any shell attaching to a running engine can rebuild its
view purely from a checkpoint snapshot plus the event stream.

---

## 3. Job orchestration v2 (the centerpiece)

This replaces `InProcessJobRunner` entirely. The new module is
`apps/api/src/echodraft_api/orchestrator/` (new package); `jobs.py` shrinks to a
compatibility shim during migration (§9).

### 3.1 Problem being solved

`InProcessJobRunner.run_inline` runs one Python callable to completion under a
2-thread pool. `StructureService.extract`
([`structure.py:77`](../../apps/api/src/echodraft_api/structure.py)) is that
callable for the whole book: it compiles structure, refines with the LLM,
discovers cast, and attributes speakers — all in one synchronous call, with
every Ollama request a blocking `urllib` POST. Consequences, all confirmed in
the last-job analysis: 6h57m wall clock, ~500–1500 sequential LLM calls, and a
restart during `llm_cast_discovery` losing the entire run three times before one
finally completed.

The fix is to model production as a **checkpointed DAG of stages**, where each
stage **fans out into independent units of work** dispatched onto **bounded,
resource-class-specific worker pools**, with **durable per-unit completion
records** so restart resumes mid-stage.

### 3.2 Stage graph model

A **stage** is a node in a directed acyclic graph. It declares:

- `inputs`: manifests it consumes (by manifest type + scope).
- `outputs`: the manifest(s) it emits.
- `resource_class`: which worker pool its units run on (`cpu`, `llm`, `tts`,
  `subprocess`, `audiogen`).
- `plan(scope) -> [Unit]`: pure function that enumerates the units of work for a
  scope from durable state (must be deterministic and idempotent — replannable
  after a restart).
- `run_unit(unit) -> UnitOutput`: executes one unit; must be side-effect-safe to
  re-run (writes are keyed by the unit's content hash).
- `reduce(scope, [UnitOutput]) -> Manifest`: folds unit outputs into the stage
  manifest once all units of the scope are complete.

A **unit** is the atomic dispatchable job. Its granularity is per stage:

| Stage | Unit granularity | Typical count (500-page book) |
|---|---|---|
| ingestion / OCR | page | 100–500 |
| structure compile | chapter (CPU) | 5–60 |
| structure LLM refine | scene window / atom batch (~3200 chars) | 200–800 |
| cast discovery | scene window (~6000 chars) | 100–400 |
| cast dedup | candidate pair / cluster | tens–hundreds |
| speaker attribution | scene window (~20 seg / 5000 chars) | 300–900 |
| direction | scene window | 100–400 |
| segment render (TTS) | segment | thousands |
| chapter assembly | chapter | 5–60 |
| sound design | scene cue | tens–hundreds |

Stage dependencies (edges) are declared, not implied by call order:

```text
ingest ──> structure ──> cast_discovery ──> speaker_attribution ──> direction ──┐
                              │                                                  │
                              └──> (book-level cast reconcile) <──────┐          │
                                                                      │          v
                                            casting (voice assign) <──┘   segment_render
                                                                             │
                                                          chapter_assembly <─┴─ sound_design
                                                                             │
                                                                           qa ──> export
```

Precise dependency semantics — including which stages need whole-book context —
are in §5.

### 3.3 Work-queue design

One **priority queue** feeds a set of **bounded worker pools, one per resource
class**. Sizing is per class because the bottleneck differs:

| Pool | Bound (default) | Why |
|---|---|---|
| `cpu` | `os.cpu_count()` | parsing/segmentation is CPU-bound and embarrassingly parallel per chapter |
| `llm` | probed (see below), start 2 | the local model server (Ollama) is the scarce resource; over-subscription only adds queue latency and thrashes VRAM |
| `tts` | 1–N by engine + VRAM | resident TTS worker holds a single lock today; target runs N workers when the engine + hardware allow (see [`../pipeline/tts/tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)) |
| `subprocess` | 2–4 | OCR/ffmpeg are process-spawns; bounded to avoid I/O and memory storms |
| `audiogen` | 1 | generative audio is VRAM-heavy; usually serialized behind TTS |

Pools are backed by the standard-library `concurrent.futures` /
`asyncio` — **no new runtime dependency** (local-first, single-binary
packaging). Units are `asyncio` tasks; blocking calls (subprocess, `urllib`
Ollama, ONNX synthesis) run via `loop.run_in_executor` on the pool's dedicated
`ThreadPoolExecutor`, so the pool's `max_workers` *is* the concurrency bound.

**Adaptive concurrency sizing for the `llm` pool.** The right LLM concurrency
depends on model size, quantization, and GPU/CPU (a 4B model on an RTX 4090 vs.
CPU-only differ by 10x). Rather than hardcode, probe and adapt:

```text
def size_llm_pool(server):
    # 1. Probe: fire K identical warmup prompts at concurrency c = 1, 2, 4, ...
    #    measuring aggregate tokens/sec until throughput stops improving.
    best_c, best_tps = 1, throughput(server, concurrency=1)
    for c in [2, 4, 8]:
        tps = throughput(server, concurrency=c)
        if tps < best_tps * 1.10:   # <10% gain: saturated
            break
        best_c, best_tps = c, tps
    # 2. Guard on memory pressure reported by the inference runtime (4.4).
    return clamp(best_c, 1, server.max_parallel_by_vram())
```

The result is cached in `local_ai` state keyed by `(model_id, hardware
signature)` so the probe runs once per machine/model, not per job. During a run
the pool uses **AIMD** (additive-increase / multiplicative-decrease): on
sustained low latency, +1 worker up to the probed ceiling; on timeout or
out-of-memory signal, halve concurrency. This keeps the machine responsive and
prevents the "page unresponsive" symptom from starving the UI thread's server.

### 3.4 Checkpoint / resume

Every unit produces a durable **completion record** *before* its output is
considered committed. The unit key is a **content hash**, extending the existing
`render_key` pattern (already `sha256(json(payload))` over
text/voice/direction/provider identity in
[`rendering.py:69`](../../apps/api/src/echodraft_api/rendering.py)) to *all*
stages:

```text
unit_key = sha256(canonical_json({
    "stage": stage_id,
    "stage_version": stage_algo_version,   # bump to force recompute on algo change
    "scope": {"project": pid, "chapter": cid, "scene": sid, ...},
    "inputs": input_content_hashes,        # hashes of the input manifests/text spans
    "model": model_id_and_version,         # for llm/tts/audiogen units; else null
    "params": stage_params,                # max_chars, window size, seed, ...
}))
```

Resume algorithm on job start (whether fresh or after a crash):

```text
def run_stage(stage, scope):
    units = stage.plan(scope)                      # deterministic re-plan
    for u in units:
        cp = checkpoints.get(u.unit_key)
        if cp and cp.status == DONE:               # idempotent skip
            continue                               # output already durable
        enqueue(u)                                 # (re)run only missing/failed units
    await all_units_terminal(units)
    if all(status == DONE):
        stage.reduce(scope, load_outputs(units))   # emit stage manifest
        checkpoints.mark_stage(stage, scope, DONE)
```

Because `plan()` is deterministic and `unit_key` is content-addressed, a restart
re-plans the same units, finds most already `DONE`, and re-enqueues only the
handful that were in-flight or failed. **A restart during
`llm_cast_discovery` now resumes at the next incomplete window instead of losing
6+ hours.** This directly closes the open question in
[`end-to-end-workflow-architecture.md`](end-to-end-workflow-architecture.md)
("Should long-running structure jobs persist phase checkpoints...").

On engine startup, `JobRepository.reconcile_interrupted` (called in
[`container.py:65`](../../apps/api/src/echodraft_api/container.py)) changes
meaning: instead of marking `RUNNING` jobs `FAILED`, it marks them `RESUMABLE`
and the orchestrator re-attaches, replans, and continues.

### 3.5 Prompt / result caching layer

A **content-addressed cache** sits in front of every inference call so reruns
are near-free. The cache key is the inference-relevant subset of the unit key:

```text
cache_key = sha256(canonical_json({
    "kind": "llm" | "tts" | "audiogen" | "embedding",
    "model": model_id_and_version,
    "schema": prompt_schema_id,        # the JSON schema / task template id
    "input_hash": sha256(prompt_input),
    "params": {temperature, seed, format, ...},
}))
```

Value = the **validated** output (LLM calls only cache after JSON-schema
validation passes — invalid outputs are never cached, matching the current
fail-closed contract). Storage: a `inference_cache` table (key, kind, model,
value_path or inline JSON, bytes, created_at, hit_count, last_hit_at). Large
values (TTS WAVs) reference filesystem paths — **never audio blobs in SQLite**.
Small values (LLM JSON) may inline.

Effect on the measured run: the 971 Ollama-assisted attribution rows and
hundreds of dedup adjudications become cache hits on any rerun after an edit that
does not change their input spans. Combined with per-unit checkpointing, a
"re-run structure after fixing front matter" goes from 7 hours to the delta.

Eviction is LRU by bytes with a configurable ceiling (`ECHODRAFT_CACHE_MAX_GB`,
default e.g. 5 GB); TTS/audiogen values also get a filesystem GC pass. The cache
is a *performance* layer, not a source of truth — deleting it only costs
recompute, never correctness.

### 3.6 Progress & event push

Replace the 5 recursive `setTimeout` polling loops (import 750ms, structure
1000ms, production 500ms, kokoro 750ms, model-install 900ms — the primary
"page unresponsive" cause per the UI research) with a **single server-push event
stream**.

- **Transport:** Server-Sent Events primary (`GET /api/v1/events?...`), one long
  loopback connection, trivially proxied by every shell. WebSocket is an
  optional upgrade for bidirectional control; SSE covers all progress needs.
- **Source:** an in-engine **event bus**. Every stage/unit transition publishes
  an event; the SSE endpoint is a subscriber that filters by
  project/job/scope. Events are also **persisted** to a `job_events` table so a
  late-attaching or reconnecting client can replay from a cursor (`Last-Event-ID`).

Event schema (JSON, versioned, one envelope):

```json
{
  "schemaVersion": "1.0.0",
  "eventId": 84213,
  "ts": "2026-07-07T12:00:00.123Z",
  "jobId": "job_3c8fbf0189cd4c8e",
  "projectId": "proj_853c19aa7bbb4706",
  "type": "unit.completed",
  "stage": "speaker_attribution",
  "scope": {"chapterId": "chap_002", "sceneId": "scene_014"},
  "payload": {
    "unitKey": "b1946ac9...",
    "status": "done",
    "durationMs": 3120,
    "cacheHit": false
  }
}
```

Event `type` taxonomy:

| type | meaning |
|---|---|
| `job.queued` / `job.running` / `job.succeeded` / `job.failed` / `job.canceled` / `job.resumed` | job lifecycle |
| `stage.started` / `stage.progress` / `stage.completed` | per-stage; `stage.progress` carries `{done, total, failed}` |
| `unit.started` / `unit.completed` / `unit.failed` / `unit.retrying` | per-unit fan-out; enables live scene-level progress |
| `artifact.ready` | a chapter WAV / manifest is durable and playable (drives progressive audio, §5) |
| `issue.opened` / `issue.resolved` | review-queue deltas |

Clients subscribe once and update surgically. This, plus virtualization and
memoization on the client (see
[`../ui/frontend-architecture.md`](../ui/frontend-architecture.md)), is what
removes the 1–2×/sec full-tree re-render.

### 3.7 Cancellation, retry, failure isolation

- **Cancellation** is cooperative: `POST /api/v1/jobs/{id}/cancel` sets the job's
  cancel flag; each pool checks it between units and stops enqueuing new work.
  In-flight units are allowed to finish (their outputs are checkpointed and thus
  not wasted) unless they expose a hard-kill (subprocess `terminate()`). State
  becomes `CANCELED`, fully resumable later.
- **Retry with backoff** is per-unit, not per-job. Transient failures (Ollama
  connection reset, subprocess timeout, ffmpeg hiccup) retry with exponential
  backoff + jitter, capped:

  ```text
  attempt n: wait = min(base * 2**(n-1), cap) * jitter(0.5..1.5)
  base=1s, cap=30s, max_attempts=4  (LLM/subprocess)
  ```

- **Failure isolation** is the rule that one bad unit cannot kill the job. A unit
  that exhausts retries is marked `FAILED`, its scope gets a durable `issue`
  (matching the current "LLM cast discovery skipped a segment window" pattern —
  98 such issues in the real run were already handled this way), and the stage
  continues. A stage completes as `completed_with_issues` when some units failed
  but the manifest is still coherent; downstream stages consume it and surface
  the gaps as review work. The job only fails if a **structural precondition**
  fails (e.g. no canonical source), never because of one noisy scene window.

---

## 4. Inference runtime

The inference runtime is the layer that owns *models and hardware*. Today this
is scattered: Ollama access is a blocking `urllib` POST in `local_llm.py`, TTS
is a single-lock resident worker in `tts_worker.py`, and there is **no GPU path
anywhere**. The target consolidates these behind one abstraction with real
hardware awareness.

### 4.1 Provider abstraction

Generalize the existing `TtsProvider` ABC (`tts_providers.py`) into a family of
inference-provider interfaces, all sharing lifecycle and health contracts:

```python
class InferenceProvider(Protocol):
    kind: Literal["llm", "embedding", "tts", "audiogen"]
    def readiness(self) -> Readiness: ...          # installed? loaded? healthy?
    def capabilities(self) -> Capabilities: ...     # e.g. direction_support, max_ctx
    def load(self, model_id: str) -> None: ...
    def unload(self, model_id: str) -> None: ...
    def infer(self, request) -> Result: ...         # schema-validated for LLM
```

Concrete providers: `OllamaLlmProvider` (today's `qwen3:4b`, JSON-schema
constrained), `OllamaEmbeddingProvider` (`qwen3-embedding`), the existing TTS
adapters (Mock, ManagedKokoroOnnx, Piper, XTTS-v2), and future
`AudioGenProvider`s for generative sound design. Because the provider interface
is uniform, the orchestrator's `llm`/`tts`/`audiogen` pools are provider-agnostic
and the Model Center can swap implementations without touching stage code. The
abstraction also leaves a clean seam for an **optional** cloud provider (never
mandatory) per the local-first constraint.

### 4.2 Local model server management

The engine owns the lifecycle of the local model server (Ollama today):

- **Discovery/launch:** detect a running server at `ollama_base_url`
  ([`config.py:24`](../../apps/api/src/echodraft_api/config.py)); if absent and
  installed via Model Center, launch it as a managed child process and wait for
  health. On engine shutdown, managed servers are stopped.
- **Concurrent requests:** replace the one-shot blocking `urllib` call with a
  small connection pool sized to the probed `llm` concurrency (§3.3). Requests
  carry the JSON-schema `format`, `temperature=0`, and a seed (§8). Ollama
  supports parallel requests via `OLLAMA_NUM_PARALLEL`; the engine sets it to
  match the pool bound at launch.
- **Abstraction over Ollama:** the provider interface means llama.cpp,
  MLX (Apple), or a bundled runtime can replace Ollama per platform without
  changing stages — important because iOS cannot run Ollama and will use an
  on-device runtime (see
  [`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md)).

### 4.3 GPU detection & scheduling

A `HardwareProbe` runs once at startup and on Model Center changes, producing a
durable `hardware_signature`:

```text
probe():
  - CUDA:      nvidia-smi / torch.cuda -> VRAM, device count
  - Metal:     macOS + Apple Silicon -> unified memory
  - DirectML:  Windows non-NVIDIA GPUs
  - ROCm:      AMD on Linux (best-effort)
  - CPU:       always available fallback (cores, RAM)
  -> {backend, vram_gb, ram_gb, device_count, tier}  (tier: low|mid|high)
```

The signature drives three decisions: (1) the adaptive pool ceilings (§3.3);
(2) engine tiering — which TTS/LLM/audiogen models are eligible (see
[`../pipeline/tts/tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md));
(3) fixing the known bug that XTTS-v2 runs with `gpu=False` hardcoded — the
provider must read the probe and enable GPU when present. **CPU is always a
correct fallback**, never a crash. The scheduler assigns GPU-bound units
(TTS, audiogen, large LLM) to avoid co-resident VRAM contention: `tts` and
`audiogen` pools share a VRAM budget and are serialized when their combined
footprint would exceed it.

### 4.4 Model lifecycle & memory pressure

Models are download→verify→load→unload managed against a **VRAM/RAM budget**:

```text
def ensure_loaded(model_id):
    if loaded(model_id): touch_lru(model_id); return
    need = model_footprint(model_id)
    while free_vram() < need:
        victim = lru_unloadable_model()      # never evict a model with in-flight units
        if victim is None: raise MemoryPressure   # -> unit retries later, or CPU tier
        unload(victim)
    load(model_id); touch_lru(model_id)
```

This lets a machine juggle an LLM + a TTS model + an audiogen model without
OOM: idle models are unloaded under pressure and reloaded on demand. Download and
verification (checksum-pinned, e.g. kokoro-onnx 0.4.7) remain the Model Center's
job (§4.5).

### 4.5 Relationship to the Model Center

The **Model Center** (`local_ai/service.py` + `model_catalog.yaml`, documented in
[`local-ai/model-center.md`](local-ai/model-center.md)) stays the declarative
catalog and installer — it is *the* mechanism that satisfies the product
requirement that every dependency is "internally handled/downloaded" with no
manual installs. The inference runtime is its **consumer**: the Model Center
installs/verifies and records `ModelInstallationRecord`; the runtime reads that
state to know what is loadable, then owns load/unload/scheduling. The catalog
gains entries for: production TTS engines, generative-audio models, GPU runtime
packages (CUDA/Metal/DirectML shims), and per-tier model variants. See
[`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md)
for the per-platform download manager.

---

## 5. Progressive pipeline (design for perceived speed)

The single biggest perceived-speed win is **chapter-level streaming**: push
chapter 1 all the way to audio while later chapters are still being extracted.
Because stages fan out per chapter/scene (§3.2) and the event bus emits
`artifact.ready` (§3.6), the orchestrator can schedule by **chapter as the unit
of flow**, not by book-wide stage barriers.

```text
time ─────────────────────────────────────────────────────────────────►
ch1  ingest│struct│cast'│attrib'│cast'│direction│render│assemble│▶AUDIO
ch2        │ingest│struct │cast' │attrib'│direction│render│assemble│▶AUDIO
ch3               │ingest │struct│cast'  │attrib' │direction│render│...
                          ▲                                   ▲
                   later chapters still extracting      user already listening
```

### 5.1 Stage dependencies: what genuinely needs whole-book context

Most stages are **chapter-local** and can run as soon as their chapter's inputs
exist. Two things genuinely need the whole book:

1. **Cast de-duplication / identity resolution.** "Liz" in chapter 1 and
   "Elizabeth" in chapter 9 are one character. A per-chapter cast pass cannot
   know that. (The real run's 601 candidates / 435 possible duplicates are
   exactly this cross-chapter identity problem.)
2. **Voice consistency.** A character must sound the same across the whole book;
   voice assignment (see
   [`../pipeline/casting/automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md))
   depends on the reconciled global cast.

### 5.2 Provisional-then-reconcile

Handle whole-book context **without blocking**, using the codebase's existing
patchability principle:

- **Provisional per-chapter pass.** Each chapter runs cast discovery + attribution
  + casting against a **provisional local cast** and a **provisional voice
  assignment**. Chapter 1 renders and becomes listenable in minutes with a
  correct-for-now voice map.
- **Book-level reconciliation pass.** As later chapters land, a low-priority
  `cast_reconcile` stage runs against the growing global mention ledger (the
  durable ledger already exists — see Cast Discovery in
  [`end-to-end-workflow-architecture.md`](end-to-end-workflow-architecture.md)),
  merges aliases into canonical characters, and produces the definitive voice
  map.
- **Patch, don't regenerate.** Reconciliation emits *targeted invalidations*: only
  segments whose resolved character/voice actually changed are re-rendered
  (segment-first invalidation + append-only render history already guarantee
  this is safe and cheap). Most segments — narration and unambiguous speakers —
  never change, so reconciliation typically re-renders a small fraction.

```text
def reconcile_cast(project):
    global_cast = merge_ledger(all_chapter_mentions)   # cross-chapter identity
    voice_map   = assign_voices(global_cast)           # deterministic, book-wide
    for seg in segments:
        new_voice = resolve_voice(seg, voice_map)       # override > attrib > narrator
        if new_voice != seg.active_render.voice:
            invalidate(seg)          # append-only stale, enqueue targeted re-render
    emit casting_manifest (reconciled)
```

This makes the pipeline feel instant (audio in minutes) while remaining
book-accurate (voices converge as reconciliation completes). Stage-internal
algorithms — LLM-first extraction, confidence gating to minimize flags,
scene-first review — are specified in
[`extraction-pipeline-v2.md`](extraction-pipeline-v2.md).

### 5.3 Scheduling policy

The scheduler interleaves for latency-to-first-audio: chapter 1's full path is
prioritized to completion; remaining chapters extract in parallel on the `cpu`
pool; `cast_reconcile` is a **rolling** low-priority stage that re-runs as new
chapters complete rather than once at the end. `render`/`tts` units for
already-reconciled chapters take priority over speculative renders of
not-yet-reconciled ones, so re-render churn is minimized.

---

## 6. Data model & storage impact

All additions respect the hard constraints: SQLite for metadata only, artifacts
+ manifests on the filesystem, **no audio blobs in the DB**, append-only render
history. New tables are additive; migrations are Alembic
([`libs/db/alembic.ini`](../../libs/db/alembic.ini)).

### 6.1 New / changed tables

```text
job_checkpoints
  unit_key TEXT PRIMARY KEY        -- content hash (§3.4)
  job_id, project_id, stage, stage_version
  scope_json                       -- {chapter, scene, ...}
  status TEXT                      -- pending|running|done|failed
  attempt INT, last_error TEXT
  output_ref TEXT                  -- manifest/artifact path (NOT a blob)
  created_at, updated_at
  INDEX (job_id, stage, status)

inference_cache
  cache_key TEXT PRIMARY KEY       -- (§3.5)
  kind, model_id, model_version, schema_id
  value_json TEXT NULL             -- small validated outputs inline
  value_path TEXT NULL             -- large outputs (WAV) on filesystem
  bytes INT, hit_count INT, created_at, last_hit_at
  -- exactly one of value_json / value_path is set; audio always value_path

job_events
  event_id INTEGER PRIMARY KEY AUTOINCREMENT   -- monotonic cursor for replay
  job_id, project_id, type, stage
  scope_json, payload_json, ts
  INDEX (job_id, event_id)         -- SSE replay from Last-Event-ID
```

Changed: `jobs` gains `state` values `RESUMABLE` and `CANCELED`, a
`cancel_requested` flag, and a `stage_cursor` (which stage/scope is active).
`VoiceProfileRecord` gains real metadata columns (gender, age band, timbre,
accent, energy) to replace the regex-guessed Kokoro-prefix facets — detailed in
[`../pipeline/casting/automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md).

### 6.2 Manifest spec additions

Extends [`pipeline-manifest-spec.md`](pipeline-manifest-spec.md) (all additive,
version-bumped):

- **Common envelope** gains `unitKeys[]` (the units that produced the manifest),
  `inputHashes` (promoted from optional to required for reproducibility), and
  `runtime` `{modelId, modelVersion, seed, hardwareSignature}` for determinism
  (§8).
- **New `run_report_manifest.json`** (§8): per-job timing per stage/unit, cache
  hit-rate, retries, failures, wall-clock, and the perceived-speed metric
  (time-to-first-audio).
- **`casting_manifest.json`** gains a `provisional` boolean and a
  `reconciledFrom[]` list linking provisional per-chapter casts to the final
  reconciled cast (§5.2).
- **`structure_manifest.json`** and downstream manifests reference their stage
  fan-out (`unitCount`, `unitsFailed`) so partial completion is visible.

### 6.3 Migration notes

- Three new tables via one additive Alembic revision; no changes to existing
  render/segment tables (append-only history is untouched).
- The `render_key` column and its partial-unique index generalize into the
  `unit_key` concept but the existing column stays — segment renders remain the
  authority for audio lineage; `job_checkpoints` references them by path.
- Verify against a disposable DB per CLAUDE.md
  (`ECHODRAFT_DATABASE_URL=sqlite:///./.tmp/echodraft-migration.db uv run alembic
  -c libs/db/alembic.ini upgrade head`).

---

## 7. API surface impact

The API stays a thin transport (§2); these are the contract changes. Full shapes
land in [`../api/api-spec.yaml`](../api/api-spec.yaml).

### 7.1 Pagination on list endpoints (mandatory)

Every list endpoint that can return thousands of rows gains cursor pagination —
today none paginate, which forces the client to load a whole chapter's timeline
or all 601 characters at once (a root cause of the UI freeze):

- `GET /api/v1/projects/{id}/characters` ([`main.py:1114`](../../apps/api/src/echodraft_api/main.py))
- `GET /api/v1/projects/{id}/chapters/{cid}/segments` (segment timeline)
- `GET /api/v1/projects/{id}/issues` ([`main.py:1830`](../../apps/api/src/echodraft_api/main.py))

Contract: `?limit=&cursor=` → `{items, nextCursor, total}`. The client pairs this
with virtualization (see
[`../ui/frontend-architecture.md`](../ui/frontend-architecture.md)).

### 7.2 Event stream endpoint (new)

```text
GET /api/v1/events?projectId=&jobId=&stage=      (SSE, text/event-stream)
  Headers: Last-Event-ID: <eventId>   -> replay from cursor (§3.6)
  Emits the §3.6 event envelope; keep-alive comments every ~15s.
```

Replaces all polling loops. Optional `WS /api/v1/ws` for bidirectional control.

### 7.3 Job control (new / changed)

```text
POST   /api/v1/projects/{id}/jobs        {type, params}   -> Job (submit to DAG)
POST   /api/v1/jobs/{jobId}/cancel                        -> Job (CANCELED)
POST   /api/v1/jobs/{jobId}/retry                         -> Job (re-enqueue failed units only)
POST   /api/v1/jobs/{jobId}/resume                        -> Job (RESUMABLE -> RUNNING)
GET    /api/v1/jobs/{jobId}                               -> Job + stage/unit progress summary
GET    /api/v1/jobs/{jobId}/report                        -> run_report_manifest (§8)
```

Existing `GET /api/v1/jobs/{jobId}` ([`main.py:639`](../../apps/api/src/echodraft_api/main.py))
and `GET /api/v1/projects/{id}/jobs` ([`main.py:647`](../../apps/api/src/echodraft_api/main.py))
stay (backward compatible) but their `Job` payload gains the fan-out progress
`{stages:[{id, done, total, failed, status}]}`.

---

## 8. Cross-cutting concerns

### Observability

- **Local run reports.** Every job emits `run_report_manifest.json` (§6.2): wall
  clock, per-stage and per-unit timing, cache hit-rate, retries, failures, and
  **time-to-first-audio**. This is the artifact you diff to prove the 6h57m run
  became minutes-to-first-audio. Exposed at `GET /api/v1/jobs/{id}/report`.
- **Structured logs + event log.** The `job_events` table *is* a durable
  observability stream; logs correlate by `jobId`/`unitKey`.
- **Debug bundles** (already an architectural goal in
  [`architecture.md`](architecture.md)) gain the checkpoint + cache state for a
  failed job so a run can be reproduced offline.

### Determinism & reproducibility

- **Seeds** are set on every stochastic inference call (LLM `temperature=0` +
  fixed seed today; TTS/audiogen seeds where the engine supports them) and
  recorded in the manifest `runtime` block.
- **Model version pinning** in manifests: `modelId + modelVersion +
  hardwareSignature` are captured per unit, so a manifest names exactly which
  models produced it. The `stage_version` field in `unit_key` (§3.4) forces
  recompute when an algorithm changes, so cache/checkpoint reuse can never serve
  stale-logic output.
- Reproducibility is *best-effort* across hardware (GPU kernels differ) but
  *exact* for the metadata/decision layer (LLM JSON decisions are deterministic
  at temp 0 + seed), which is what patch loops depend on.

### Testing strategy

- **Scale fixtures.** A synthetic **500-page book** generator (deterministic:
  N chapters, M scenes, seeded dialogue with known speakers) lives in
  `test-assets/` (git-ignored) with a small committed generator script. It is the
  standard load for: orchestrator resume tests, pool-sizing tests, cache
  hit-rate tests, and the time-to-first-audio benchmark.
- **Resume tests** kill the orchestrator mid-stage and assert the rerun completes
  with zero duplicated inference (checkpoint hit-rate ~100% on unchanged units).
- **Failure-isolation tests** inject a poisoned scene window and assert the job
  completes `completed_with_issues` with exactly one issue, not a failed job.
- **Determinism tests** run the same fixture twice and diff decision manifests
  (must be identical) while tolerating audio-sample differences.
- Standard gates per CLAUDE.md: `uv run pytest`, `uv run ruff check .`,
  `uv run mypy ...`, plus `npm run web:*` for the client contract.

---

## 9. Migration path from the current codebase

Incremental and **shippable at every step** — the app keeps working after each.

1. **Introduce the orchestrator package alongside the old runner.** Add
   `apps/api/src/echodraft_api/orchestrator/` with `Stage`, `Unit`, work-queue,
   and checkpoint store. Keep
   [`jobs.py`](../../apps/api/src/echodraft_api/jobs.py) `InProcessJobRunner`
   working; wire the orchestrator only for *new* code paths. No behavior change
   yet. (New Alembic revision for `job_checkpoints`/`inference_cache`/`job_events`.)

2. **Add the event bus + SSE endpoint; keep polling as fallback.** Implement
   `GET /api/v1/events` and persist `job_events`. The client can adopt it
   incrementally (see [`../ui/frontend-architecture.md`](../ui/frontend-architecture.md));
   polling still works until it is removed. Immediate UX win, low risk.

3. **Wrap the LLM call in the cache + provider abstraction.** Replace the raw
   `urllib` call in `local_llm.py` with `OllamaLlmProvider.infer` fronted by
   `inference_cache`. No concurrency yet — just caching + the seam. Reruns get
   cheaper immediately; the fail-closed validation contract is preserved.

4. **Fan out the structure stage.** Refactor
   [`StructureService.extract` (`structure.py:77`)](../../apps/api/src/echodraft_api/structure.py):
   the `_refine_hierarchy` LLM loop and `_run_cast_and_speaker_draft` become
   `plan()`/`run_unit()`/`reduce()` over scene-window units on the `llm` pool.
   Same for the sequential cast-discovery ([`cast_discovery.py`](../../apps/api/src/echodraft_api/cast_discovery.py))
   and speaker-attribution ([`speaker_attribution.py`](../../apps/api/src/echodraft_api/speaker_attribution.py))
   loops. This is where the 6h57m → minutes step-change lands. Checkpointing
   makes it resumable in the same change.

5. **Fan out OCR and TTS.** Parallelize the per-page OCR subprocess loop onto the
   `subprocess` pool, and lift the single-lock resident TTS worker
   ([`tts_worker.py`](../../apps/api/src/echodraft_api/tts_worker.py)) to N
   workers on the `tts` pool where the engine/hardware allow (coordinate with
   [`../pipeline/tts/tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)).

6. **Add hardware probe + GPU scheduling.** Land `HardwareProbe`, fix the
   XTTS `gpu=False` hardcode, and enable adaptive `llm` pool sizing (§3.3–3.4).

7. **Enable progressive chapter streaming + provisional-then-reconcile.** Switch
   the scheduler to chapter-flow priority and add the rolling `cast_reconcile`
   stage (§5). Requires the automatic-casting work in
   [`../pipeline/casting/automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md).

8. **Retire the old runner.** Once all job types route through the orchestrator,
   reduce `jobs.py` to a shim (or delete it), change `reconcile_interrupted` to
   mark `RESUMABLE` instead of `FAILED` ([`container.py:65`](../../apps/api/src/echodraft_api/container.py)),
   and remove client polling.

Each step is independently verifiable (§8 gates) and independently shippable.

---

## 10. Risks & open questions

**Risks**

- **SQLite write contention under high fan-out.** Thousands of checkpoint/event
  writes/sec can hit the 30s busy timeout. Mitigation: WAL (already on), batch
  checkpoint writes, and route all writes through a single writer task/queue
  (SQLite is single-writer); the pools are readers.
- **Local model server as the hard ceiling.** No amount of orchestration beats a
  slow local LLM. The adaptive pool prevents *thrash*, but throughput is
  ultimately model+hardware bound; the answer is the tiered/LLM-first extraction
  in [`extraction-pipeline-v2.md`](extraction-pipeline-v2.md) doing *fewer, better*
  calls, not just parallel ones.
- **Provisional-then-reconcile churn.** A pathological book (heavy cross-chapter
  aliasing) could trigger large re-render waves. Mitigation: reconcile
  incrementally, cap re-render batch size, and prefer voice maps that minimize
  reassignment when confidence is comparable.
- **Memory pressure with 3 model families resident** (LLM + TTS + audiogen).
  Mitigation: the VRAM-budget LRU loader (§4.4) and serializing `audiogen`
  behind `tts`.
- **Cross-platform runtime parity.** Ollama is not available on iOS; the provider
  abstraction is the hedge but a second on-device LLM runtime is real work
  (tracked in [`../platform/cross-platform-strategy.md`](../platform/cross-platform-strategy.md)).

**Open questions**

- Should the engine expose the DAG to the UI as an editable plan (power users
  re-running one stage), or stay an opaque scheduler?
- SSE vs. WebSocket as the default in embedded webviews — does any target
  platform's webview mishandle long-lived SSE?
- Where is the right cache-size default per hardware tier, and should the cache
  persist across projects (shared model warmups) or stay project-scoped?
- Should `cast_reconcile` ever *block* the first export, or is a "voices still
  converging" advisory sufficient for a listenable draft?
- Do we checkpoint at sub-unit granularity for very long TTS segments, or is
  segment-level the right floor (keeping the segment as the atomic unit)?
