# Automatic Casting Auto-chain and Override Plan

**Goal:** Make automatic casting the safe zero-click continuation of extraction without ever
silently replacing a human voice choice.

**Architecture:** Add assignment lock and decision-link columns, repair prior automatic rows from
active decisions, and lock all remaining legacy hand assignments. Auto-cast treats locked character
and narrator choices as fixed constraints, writes new assignments through the existing mutation
path with their decision IDs, and emits a versioned casting manifest. Structure extraction invokes
the stage behind the v2 runtime flag after cast discovery and attribution stabilize. Manual voice
overrides create explainable decisions when backed by a catalog voice and enforce narrator reuse.

**Tech Stack:** SQLAlchemy/Alembic, FastAPI jobs, feature flags, manifest artifacts, pytest.

---

1. Add migration/model/repair coverage for assignment locks and casting-decision links.
2. Preserve legacy hand-cast narrator and character choices; skip locked rows on every rerun.
3. Extend manual assignment with lock semantics, narrator-reuse enforcement, and decision evidence.
4. Auto-chain casting after attribution under the v2 flag and write the versioned manifest.
5. Run migration parity, full backend tests, lint, and strict type checking.
