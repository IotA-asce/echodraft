# Extraction Confidence and Flag Model Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist calibrated three-tier extraction decisions and replace per-row review floods with fewer than twenty durable grouped review tasks per book.

**Architecture:** Add the consolidated v2 schema columns and `review_tasks` table through an additive migration and SQLite repair path. A feature-flagged confidence service classifies structure and attribution rows, groups flag-tier members by cause/scope, links every flagged attribution to exactly one open task, and exposes tasks through typed APIs while retaining legacy warnings for compatibility.

**Tech Stack:** Python 3.12, SQLAlchemy/Alembic, FastAPI, Pydantic, pytest, Ruff, mypy.

---

### Task 1: Schema and repository

1. Write migration tests for `review_tasks`, decision columns, indexes, and legacy SQLite repair.
2. Add migration `0032_extraction_review_tasks.py`, matching ORM fields, domain models, and repair statements.
3. Add repository create-or-fold, list, and status-update methods with stable member deduplication.
4. Run migration tests and schema-drift verification.

### Task 2: Three-tier classifier and grouped task service

1. Write unit tests for per-stage HIGH/MID thresholds, locked/manual rows, and calibrated vote confidence.
2. Write integration tests proving two low attribution rows in one scene become one task, every flag row links to it, mid/high rows remain auditable but unqueued, and reruns do not duplicate members.
3. Implement `ConfidenceReviewService` and feature flag `ECHODRAFT_CONFIDENCE_V2_ENABLED`.
4. Chain classification after flagged attribution/structure stages without affecting v1 defaults.

### Task 3: Typed API, gate, and delivery

1. Add typed list/update review-task endpoints and API tests.
2. Add `--confidence-v2` to the eval harness and require fewer than twenty tasks/flags with no required steps on the committed fixture.
3. Run the full backend suite, Ruff, mypy, and migration checks.
4. Record the comparison gate, update W3.6 trackers, commit, merge, and push without staging `.env` or unrelated lockfile changes.
