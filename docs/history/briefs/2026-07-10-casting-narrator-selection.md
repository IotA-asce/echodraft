# Narrator Selection Implementation Plan

**Goal:** Select and persist a commercially usable narrator before assigning any character voice.

**Architecture:** Read narration segments in book order, classify first- versus third-person POV
with an explicit first-person-pronoun ratio, rank eligible measured catalog voices against the
requested style preset, and link the winning catalog identity to a project voice profile and the
existing production settings. W4.3 will add the append-only decision evidence record.

**Tech Stack:** SQLAlchemy, Pydantic voice catalog models, FastAPI service container, pytest.

---

1. Add a pure POV detector with the documented pronoun-ratio sanity check.
2. Select only commercially usable measured catalog entries with deterministic tie-breaking.
3. Persist an idempotent project narrator profile through production settings.
4. Verify first-person classification, catalog linkage, rerun idempotence, lint, and types.
