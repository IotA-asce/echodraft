# TTS Engine Host Implementation Plan

**Goal:** Run resident TTS engines through the orchestrator's bounded TTS pool with device-aware,
multi-worker lifetime management.

**Architecture:** Introduce a provider-neutral `EngineHost` that owns N lazy resident workers,
dispatches requests round-robin through the existing adaptive TTS execution pool, aggregates
status, and stops every worker on configuration changes or shutdown. Keep the managed Kokoro API
unchanged on top of the host. Derive the runtime device from the hardware probe and pass it into
XTTS instead of hardcoding CPU execution.

**Tech Stack:** Python subprocess JSON protocol, ThreadPoolExecutor-backed orchestrator pool,
hardware probe, pytest.

---

1. Add device selection and bounded TTS-worker recommendations to the hardware layer.
2. Generalize the resident manager into an N-worker `EngineHost` without changing adapters.
3. Inject the orchestrator TTS pool/device through the application container.
4. Make XTTS choose CPU/GPU from the probed device and expose host status additively.
5. Verify worker reuse, real two-process concurrency, shutdown, provider compatibility, lint,
   and strict typing.
