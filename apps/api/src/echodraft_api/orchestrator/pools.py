from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypeVar

from .hardware import (
    HardwareProbe,
    HardwareSnapshot,
    recommended_llm_workers,
    recommended_tts_workers,
)

T = TypeVar("T")


@dataclass(frozen=True)
class PoolStatus:
    name: str
    max_workers: int
    active: bool


@dataclass(frozen=True)
class ModelLease:
    model_key: str
    estimated_vram_gib: float
    loaded_at: datetime
    last_used_at: datetime


@dataclass(frozen=True)
class ModelLoadResult:
    model_key: str
    loaded_keys: list[str]
    evicted_keys: list[str]
    total_vram_gib: float
    over_budget: bool


@dataclass(frozen=True)
class ModelLoaderStatus:
    budget_vram_gib: float
    total_vram_gib: float
    loaded: list[ModelLease] = field(default_factory=list)


class AdaptiveWorkerPool:
    def __init__(self, name: str, max_workers: int) -> None:
        self.name = name
        self.max_workers = max(1, max_workers)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=f"echodraft-{name}",
        )

    def run(self, operation: Callable[[], T]) -> T:
        return self._executor.submit(operation).result()

    def status(self) -> PoolStatus:
        return PoolStatus(name=self.name, max_workers=self.max_workers, active=True)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class SingleWriterQueue:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def run(self, operation: Callable[[], T]) -> T:
        with self._lock:
            return operation()


class VramBudgetModelLoader:
    def __init__(self, budget_vram_gib: float) -> None:
        self.budget_vram_gib = max(0.1, budget_vram_gib)
        self._lock = threading.Lock()
        self._leases: dict[str, ModelLease] = {}

    def touch(self, model_key: str, estimated_vram_gib: float) -> ModelLoadResult:
        now = datetime.now(UTC)
        size = max(0.0, estimated_vram_gib)
        evicted: list[str] = []
        with self._lock:
            existing = self._leases.get(model_key)
            self._leases[model_key] = ModelLease(
                model_key=model_key,
                estimated_vram_gib=size,
                loaded_at=existing.loaded_at if existing else now,
                last_used_at=now,
            )
            while self._total_vram_gib() > self.budget_vram_gib and len(self._leases) > 1:
                victim = min(
                    (lease for lease in self._leases.values() if lease.model_key != model_key),
                    key=lambda lease: lease.last_used_at,
                )
                evicted.append(victim.model_key)
                del self._leases[victim.model_key]
            return ModelLoadResult(
                model_key=model_key,
                loaded_keys=sorted(self._leases),
                evicted_keys=evicted,
                total_vram_gib=self._total_vram_gib(),
                over_budget=self._total_vram_gib() > self.budget_vram_gib,
            )

    def unload(self, model_key: str) -> None:
        with self._lock:
            self._leases.pop(model_key, None)

    def status(self) -> ModelLoaderStatus:
        with self._lock:
            leases = sorted(self._leases.values(), key=lambda lease: lease.model_key)
            return ModelLoaderStatus(
                budget_vram_gib=self.budget_vram_gib,
                total_vram_gib=sum(lease.estimated_vram_gib for lease in leases),
                loaded=leases,
            )

    def _total_vram_gib(self) -> float:
        return sum(lease.estimated_vram_gib for lease in self._leases.values())


class OrchestratorPools:
    def __init__(
        self,
        *,
        hardware: HardwareSnapshot,
        llm_workers: int,
        subprocess_workers: int,
        tts_workers: int,
        audiogen_workers: int,
        model_vram_budget_gib: float,
    ) -> None:
        self.hardware = hardware
        self.llm = AdaptiveWorkerPool("llm", llm_workers)
        self.subprocess = AdaptiveWorkerPool("subprocess", subprocess_workers)
        self.tts = AdaptiveWorkerPool("tts", tts_workers)
        self.audiogen = AdaptiveWorkerPool("audiogen", audiogen_workers)
        self.writer = SingleWriterQueue()
        self.model_loader = VramBudgetModelLoader(model_vram_budget_gib)

    @classmethod
    def from_probe(
        cls,
        probe: HardwareProbe,
        *,
        llm_workers_override: int | None = None,
        subprocess_workers_override: int | None = None,
        tts_workers_override: int | None = None,
        audiogen_workers_override: int | None = None,
        model_vram_budget_gib: float | None = None,
    ) -> "OrchestratorPools":
        hardware = probe.snapshot()
        default_vram_budget = hardware.gpu_vram_gib or max(1.0, (hardware.total_ram_gib or 8.0) / 2)
        return cls(
            hardware=hardware,
            llm_workers=recommended_llm_workers(hardware, llm_workers_override),
            subprocess_workers=_override_or_default(
                subprocess_workers_override,
                max(1, min(4, hardware.cpu_count)),
            ),
            tts_workers=recommended_tts_workers(hardware, tts_workers_override),
            audiogen_workers=_override_or_default(audiogen_workers_override, 1),
            model_vram_budget_gib=model_vram_budget_gib or default_vram_budget,
        )

    def statuses(self) -> list[PoolStatus]:
        return [
            self.llm.status(),
            self.subprocess.status(),
            self.tts.status(),
            self.audiogen.status(),
        ]

    def shutdown(self) -> None:
        self.llm.shutdown()
        self.subprocess.shutdown()
        self.tts.shutdown()
        self.audiogen.shutdown()


def _override_or_default(override: int | None, default: int) -> int:
    return max(1, override) if override is not None else max(1, default)
