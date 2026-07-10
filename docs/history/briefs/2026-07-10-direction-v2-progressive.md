# Direction v2 and Progressive Delivery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce profile-aware direction metadata on the shared scene-window framework and publish chapter-ready events as soon as each chapter has a usable provisional direction pass.

**Architecture:** Preserve deterministic direction as the immediate fallback, then run flagged scene-window LLM refinement concurrently with resolved speaker/profile context and strict controlled-value validation. Add stable priority ordering to orchestrator units and emit per-chapter checkpoints/events during the provisional pass so downstream rendering/mastering can consume chapter one before book-wide refinement finishes.

**Tech Stack:** Python 3.12, FastAPI service layer, Ollama structured extraction, orchestrator checkpoints/events, pytest, Ruff, mypy.

---

1. Write failing tests for priority-stable work queues and per-chapter direction-ready events.
2. Add direction/progressive flags, chapter-priority units, provisional checkpoints, and SSE events.
3. Write failing tests for parallel v2 direction MAP, Character Bible profile context, controlled-value normalization, locks, and additive manifest rows.
4. Implement concurrent refinement and final chapter events; auto-chain it after attribution only when flagged.
5. Run full backend verification and record the first-chapter readiness gate.
6. Update W3/W3.7 trackers, commit, merge, and push without staging local secrets or unrelated lockfile changes.
