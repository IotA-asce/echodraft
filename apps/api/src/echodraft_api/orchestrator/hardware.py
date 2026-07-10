from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass


BYTES_PER_GIB = 1024**3


@dataclass(frozen=True)
class HardwareSnapshot:
    cpu_count: int
    total_ram_gib: float | None
    gpu_vram_gib: float | None = None
    platform: str = ""
    machine: str = ""
    source: str = "auto"


class HardwareProbe:
    def snapshot(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            cpu_count=max(1, os.cpu_count() or 1),
            total_ram_gib=_total_ram_gib(),
            gpu_vram_gib=_gpu_vram_gib_from_env(),
            platform=platform.system().lower(),
            machine=platform.machine().lower(),
        )


def recommended_llm_workers(snapshot: HardwareSnapshot, override: int | None = None) -> int:
    if override is not None:
        return max(1, override)

    memory_gib = snapshot.gpu_vram_gib or snapshot.total_ram_gib
    cpu_cap = max(1, min(4, snapshot.cpu_count))
    if memory_gib is None:
        return min(2, cpu_cap)
    if memory_gib < 12:
        return 1
    if memory_gib < 32:
        return min(2, cpu_cap)
    return cpu_cap


def recommended_tts_workers(snapshot: HardwareSnapshot, override: int | None = None) -> int:
    if override is not None:
        return max(1, override)
    if snapshot.gpu_vram_gib:
        return 1
    if (snapshot.total_ram_gib or 0) >= 16 and snapshot.cpu_count >= 4:
        return 2
    return 1


def tts_device(snapshot: HardwareSnapshot) -> str:
    if snapshot.platform == "darwin" and snapshot.machine in {"arm64", "aarch64"}:
        return "mps"
    if not snapshot.gpu_vram_gib:
        return "cpu"
    return "mps" if snapshot.platform == "darwin" else "cuda"


def _total_ram_gib() -> float | None:
    if platform.system() == "Darwin":
        return _mac_total_ram_gib()
    if platform.system() == "Linux":
        return _linux_total_ram_gib()
    return None


def _mac_total_ram_gib() -> float | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    try:
        return int(completed.stdout.strip()) / BYTES_PER_GIB
    except ValueError:
        return None


def _linux_total_ram_gib() -> float | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    return int(parts[1]) * 1024 / BYTES_PER_GIB
    except (OSError, IndexError, ValueError):
        return None
    return None


def _gpu_vram_gib_from_env() -> float | None:
    value = os.getenv("ECHODRAFT_GPU_VRAM_GIB")
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
