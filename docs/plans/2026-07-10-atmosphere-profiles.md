# Atmosphere Profile Extraction Plan

**Goal:** Add conservative, optional scene atmosphere metadata without making sound design a
structure-extraction failure mode.

**Architecture:** Add one JSON profile column to scenes and expose it additively. Behind a runtime
flag, a deterministic evidence pass recognizes explicit weather/location/time/mood signals, then
independent per-scene local-LLM calls refine profiles in parallel when the model is available. A
strict target guard and confidence gate store `{}` on uncertainty or failure. Profiles are mirrored
into the structure manifest and extraction continues regardless of sound-profile errors.

**Tech Stack:** SQLAlchemy/Alembic, Ollama schema extraction, bounded parallel workers, pytest.

---

1. Add the scene profile column, migration, SQLite repair, and additive API field.
2. Implement deterministic evidence and controlled profile normalization.
3. Add parallel schema-constrained refinement with target/confidence guards and fail-open behavior.
4. Auto-chain behind the atmosphere flag and mirror accepted profiles into the structure manifest.
5. Verify migration parity, deterministic fallback, parallel refinement, low-confidence/error
   degradation, full backend tests, lint, and types.
