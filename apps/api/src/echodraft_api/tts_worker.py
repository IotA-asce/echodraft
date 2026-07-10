"""Resident local TTS worker processes."""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

from echodraft_domain import TtsWorkerStatus

if TYPE_CHECKING:
    from .orchestrator import AdaptiveWorkerPool

W = TypeVar("W", bound="HostedWorker")
T = TypeVar("T")


class WorkerProcessError(ValueError):
    """Raised when the resident worker process or JSON protocol breaks."""


class HostedWorker(Protocol):
    def stop(self) -> None: ...

    def status(self) -> TtsWorkerStatus: ...


class EngineHost(Generic[W]):
    """Own a bounded set of resident workers for one engine/device pair."""

    def __init__(
        self,
        *,
        engine_id: str,
        setup_mode: str,
        device: str,
        max_workers: int,
        worker_factory: Callable[[], W],
        execution_pool: AdaptiveWorkerPool | None = None,
    ) -> None:
        self.engine_id = engine_id
        self.setup_mode = setup_mode
        self.device = device
        self.execution_pool = execution_pool
        self._workers = [worker_factory() for _ in range(max(1, max_workers))]
        self._lock = threading.Lock()
        self._next_worker = 0

    def run(self, operation: Callable[[W], T]) -> T:
        with self._lock:
            worker = self._workers[self._next_worker]
            self._next_worker = (self._next_worker + 1) % len(self._workers)
        def invoke() -> T:
            return operation(worker)

        return self.execution_pool.run(invoke) if self.execution_pool else invoke()

    def stop(self) -> None:
        for worker in self._workers:
            worker.stop()

    def status(self) -> TtsWorkerStatus:
        statuses = [worker.status() for worker in self._workers]
        running = [status for status in statuses if status.state == "running"]
        stopped = [status for status in statuses if status.state == "stopped"]
        state = "running" if running else "stopped" if stopped else "idle"
        pids = [status.pid for status in [*running, *stopped] if status.pid is not None]
        errors = [status.last_error for status in statuses if status.last_error]
        return TtsWorkerStatus(
            provider=self.engine_id,
            setupMode=self.setup_mode,
            workerMode="resident",
            state=state,
            pid=pids[0] if pids else None,
            requestCount=sum(status.request_count for status in statuses),
            lastError=errors[-1] if errors else None,
            device=self.device,
            workerCount=len(self._workers),
        )


@dataclass(frozen=True)
class ManagedKokoroWorkerKey:
    python_path: Path
    wrapper_path: Path
    model_path: Path
    voices_data_path: Path
    voice_registry_path: Path


class ManagedKokoroWorker:
    def __init__(self, key: ManagedKokoroWorkerKey) -> None:
        self.key = key
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self.request_count = 0
        self.last_error: str | None = None

    def synthesize(self, text: str, voice_id: str, output: Path, speed: float) -> int:
        with self._lock:
            for attempt in range(2):
                self._ensure_started()
                try:
                    return self._send_request(text, voice_id, output, speed)
                except WorkerProcessError as error:
                    self.last_error = str(error)
                    self.stop()
                    if attempt == 1:
                        raise ValueError(str(error)) from error
            raise ValueError("Kokoro worker failed before synthesis could complete.")

    def stop(self) -> None:
        process = self._process
        self._process = None
        if not process:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def status(self) -> TtsWorkerStatus:
        process = self._process
        if not process:
            state = "idle"
            pid = None
        elif process.poll() is None:
            state = "running"
            pid = process.pid
        else:
            state = "stopped"
            pid = process.pid
        return TtsWorkerStatus(
            provider="kokoro",
            setupMode="managed_onnx",
            workerMode="resident",
            state=state,
            pid=pid,
            requestCount=self.request_count,
            lastError=self.last_error,
        )

    def _ensure_started(self) -> None:
        if self._process and self._process.poll() is None:
            return
        command = [
            str(self.key.python_path),
            str(self.key.wrapper_path),
            "--model",
            str(self.key.model_path),
            "--voices-data",
            str(self.key.voices_data_path),
            "--voice-registry",
            str(self.key.voice_registry_path),
            "--serve-json",
        ]
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _send_request(self, text: str, voice_id: str, output: Path, speed: float) -> int:
        process = self._process
        if not process or not process.stdin or not process.stdout:
            raise WorkerProcessError("Kokoro worker process is not available.")
        if process.poll() is not None:
            raise WorkerProcessError(self._process_error(process))
        payload = {
            "text": text,
            "voice": voice_id,
            "output": str(output),
            "speed": speed,
        }
        try:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
        except OSError as error:
            raise WorkerProcessError(f"Kokoro worker I/O failed: {error}") from error
        if not line:
            raise WorkerProcessError(self._process_error(process))
        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise WorkerProcessError("Kokoro worker returned malformed JSON.") from error
        if not isinstance(response, dict):
            raise WorkerProcessError("Kokoro worker returned an invalid response.")
        if not response.get("ok"):
            message = str(response.get("error") or "Kokoro worker synthesis failed.")
            self.last_error = message
            raise ValueError(message)
        sample_rate = response.get("sampleRate")
        if not isinstance(sample_rate, int):
            raise WorkerProcessError("Kokoro worker response omitted sampleRate.")
        self.request_count += 1
        self.last_error = None
        return sample_rate

    @staticmethod
    def _process_error(process: subprocess.Popen[str]) -> str:
        stderr = ""
        if process.stderr:
            try:
                stderr = process.stderr.read()
            except OSError:
                stderr = ""
        detail = stderr.strip() or "the worker stopped without details"
        return f"Kokoro worker exited unexpectedly: {detail}"


class TtsWorkerManager:
    def __init__(
        self,
        *,
        execution_pool: AdaptiveWorkerPool | None = None,
        device: str = "cpu",
    ) -> None:
        self._lock = threading.Lock()
        self._execution_pool = execution_pool
        self.device = device
        self._managed_kokoro: EngineHost[ManagedKokoroWorker] | None = None
        self._managed_kokoro_key: ManagedKokoroWorkerKey | None = None

    def synthesize_managed_kokoro(
        self,
        *,
        python_path: Path,
        wrapper_path: Path,
        model_path: Path,
        voices_data_path: Path,
        voice_registry_path: Path,
        text: str,
        voice_id: str,
        output: Path,
        speed: float,
    ) -> int:
        key = ManagedKokoroWorkerKey(
            python_path=python_path,
            wrapper_path=wrapper_path,
            model_path=model_path,
            voices_data_path=voices_data_path,
            voice_registry_path=voice_registry_path,
        )
        host = self._host_for_key(key)
        return host.run(
            lambda worker: worker.synthesize(text, voice_id, output, speed)
        )

    def stop_all(self) -> None:
        with self._lock:
            worker = self._managed_kokoro
            self._managed_kokoro = None
            self._managed_kokoro_key = None
        if worker:
            worker.stop()

    def status(self, *, provider: str, setup_mode: str | None) -> TtsWorkerStatus:
        if provider != "kokoro" or setup_mode != "managed_onnx":
            return TtsWorkerStatus(
                provider=provider,
                setupMode=setup_mode,
                workerMode="subprocess",
                state="not_applicable",
                pid=None,
                requestCount=0,
                lastError=None,
                device=self.device,
                workerCount=0,
            )
        with self._lock:
            worker = self._managed_kokoro
        if not worker:
            return TtsWorkerStatus(
                provider="kokoro",
                setupMode="managed_onnx",
                workerMode="resident",
                state="idle",
                pid=None,
                requestCount=0,
                lastError=None,
                device=self.device,
                workerCount=(
                    self._execution_pool.max_workers if self._execution_pool else 1
                ),
            )
        return worker.status()

    def _host_for_key(self, key: ManagedKokoroWorkerKey) -> EngineHost[ManagedKokoroWorker]:
        old_worker: EngineHost[ManagedKokoroWorker] | None = None
        with self._lock:
            if self._managed_kokoro and self._managed_kokoro_key == key:
                return self._managed_kokoro
            old_worker = self._managed_kokoro
            self._managed_kokoro = EngineHost(
                engine_id="kokoro",
                setup_mode="managed_onnx",
                device=self.device,
                max_workers=(
                    self._execution_pool.max_workers if self._execution_pool else 1
                ),
                worker_factory=lambda: ManagedKokoroWorker(key),
                execution_pool=self._execution_pool,
            )
            self._managed_kokoro_key = key
            host = self._managed_kokoro
        if old_worker:
            old_worker.stop()
        return host
