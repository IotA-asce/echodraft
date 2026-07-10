# Tier-A Direction Compiler Implementation Plan

**Goal:** Centralize the honest direction-to-engine translation without changing any existing
Kokoro, Piper, or XTTS response contract.

**Architecture:** Add a pure compiler that accepts a `DirectionProfile`, provider/setup identity,
and advertised capabilities. It emits engine-native controls, the exact effective-direction
metadata, and the full unsupported-control list. Managed Kokoro compiles pace to speed; Piper
compiles pace to length scale and the trailing pause to sentence silence; custom Kokoro and XTTS
remain neutral with assembly-only pauses.

**Tech Stack:** Python dataclasses, existing Pydantic direction models, pytest.

---

1. Define the pure compiled-direction contract and provider mappings.
2. Route Tier-A adapters through the compiler while preserving CLI arguments and provenance.
3. Add golden contract tests for supported, unsupported, and engine-native controls.
4. Run full backend tests, lint, and strict typing.
