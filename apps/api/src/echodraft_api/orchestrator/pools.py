from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TypeVar

from .hardware import HardwareProbe, HardwareSnapshot, recommended_llm_workers

T = TypeVar("T")


@dataclass(frozen=True)
class PoolStatus:
    name: str
    max_workers: int
    active: bool


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


class OrchestratorPools:
    def __init__(
        self,
        *,
        hardware: HardwareSnapshot,
        llm_workers: int,
    ) -> None:
        self.hardware = hardware
        self.llm = AdaptiveWorkerPool("llm", llm_workers)
        self.writer = SingleWriterQueue()

    @classmethod
    def from_probe(
        cls,
        probe: HardwareProbe,
        *,
        llm_workers_override: int | None = None,
    ) -> "OrchestratorPools":
        hardware = probe.snapshot()
        return cls(
            hardware=hardware,
            llm_workers=recommended_llm_workers(hardware, llm_workers_override),
        )

    def shutdown(self) -> None:
        self.llm.shutdown()
