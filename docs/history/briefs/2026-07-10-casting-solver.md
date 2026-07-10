# Automatic Casting Solver Implementation Plan

**Goal:** Assign a measured catalog voice to the narrator and every speaking character with
deterministic constraints and an append-only explanation trail.

**Architecture:** Extend production settings with the v2 casting controls and add append-only
casting decisions. Derive character requirements from traits and approved attributed dialogue,
reserve the narrator first, score commercially eligible catalog voices, enforce hard facet and
major-voice distinctness constraints, pool voices for minors, and intentionally route very small
walk-on roles to the narrator. Apply choices through the existing assignment path and retain the
top candidate evidence for inspection.

**Tech Stack:** SQLAlchemy/Alembic, FastAPI jobs, Pydantic, deterministic Python solver, pytest.

---

1. Add migration/model coverage for casting decisions and automatic-casting settings.
2. Implement casting-spec derivation, scoring, distinctiveness, constraint assignment, and
   append-only supersession.
3. Expose the asynchronous auto-run and typed casting-decision read APIs.
4. Verify zero-click coverage, narrator reservation, walk-on fallback, determinism, migration
   parity, full backend tests, lint, and types.
