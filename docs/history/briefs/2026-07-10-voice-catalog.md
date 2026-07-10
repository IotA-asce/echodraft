# Voice Catalog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace filename-guessed voice facets with a durable catalog populated from one-time audition audio measurements.

**Architecture:** Add a global catalog table linked optionally from project voice profiles. An idempotent audition job synthesizes a standard paragraph for each installed provider voice, stores WAV files outside the database, extracts conservative acoustic measurements locally, persists provenance/license metadata, and exposes the measured facets through the existing `VoiceProfile.facets` shape.

**Tech Stack:** Python wave/array DSP, SQLAlchemy/Alembic, FastAPI jobs, Pydantic, pytest.

---

1. Add migration/model/repository tests for catalog uniqueness and voice-profile linkage.
2. Implement local audition measurement and idempotent backfill with typed APIs.
3. Replace read-time guessed facets when a measured catalog link exists, retaining v1 fallback for old profiles.
4. Run full backend verification, update W4.1 trackers, commit, merge, and push.
