from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from echodraft_db import OrchestratorRepository
from echodraft_db.models import JobCheckpointRecord


@dataclass(frozen=True)
class Stage:
    name: str
    version: str = "1"


@dataclass(frozen=True)
class Unit:
    stage: Stage
    job_id: str
    project_id: str | None
    scope: dict[str, object] = field(default_factory=dict)
    unit_key: str | None = None

    @property
    def key(self) -> str:
        if self.unit_key:
            return self.unit_key
        payload = {
            "jobId": self.job_id,
            "projectId": self.project_id,
            "stage": self.stage.name,
            "stageVersion": self.stage.version,
            "scope": self.scope,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f"unit_{digest[:32]}"


class WorkQueue:
    def __init__(self, units: Iterable[Unit] = ()) -> None:
        self._pending: deque[Unit] = deque(units)

    def push(self, unit: Unit) -> None:
        self._pending.append(unit)

    def pop_ready(self, checkpoints: CheckpointStore) -> Unit | None:
        while self._pending:
            unit = self._pending.popleft()
            checkpoint = checkpoints.get(unit)
            if checkpoint is None or checkpoint.status in {"pending", "failed"}:
                return unit
        return None

    def __len__(self) -> int:
        return len(self._pending)


class CheckpointStore:
    def __init__(self, repository: OrchestratorRepository) -> None:
        self.repository = repository

    def get(self, unit: Unit) -> JobCheckpointRecord | None:
        return self.repository.checkpoint(unit.key)

    def mark_pending(self, unit: Unit) -> JobCheckpointRecord:
        return self._mark(unit, "pending")

    def mark_running(self, unit: Unit) -> JobCheckpointRecord:
        return self._mark(unit, "running")

    def mark_done(self, unit: Unit, *, output_ref: str | None = None) -> JobCheckpointRecord:
        return self._mark(unit, "done", output_ref=output_ref)

    def mark_failed(self, unit: Unit, error: str) -> JobCheckpointRecord:
        return self._mark(unit, "failed", last_error=error)

    def _mark(
        self,
        unit: Unit,
        status: str,
        *,
        output_ref: str | None = None,
        last_error: str | None = None,
    ) -> JobCheckpointRecord:
        return self.repository.upsert_checkpoint(
            unit_key=unit.key,
            job_id=unit.job_id,
            project_id=unit.project_id,
            stage=unit.stage.name,
            stage_version=unit.stage.version,
            scope=unit.scope,
            status=status,
            output_ref=output_ref,
            last_error=last_error,
        )
