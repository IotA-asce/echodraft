import sys
import wave
from pathlib import Path

from echodraft_api.tts_providers import ManagedKokoroOnnxAdapter
from echodraft_api.tts_worker import TtsWorkerManager
from echodraft_domain import DirectionProfile


FAKE_WORKER_SOURCE = """\
import argparse
import json
import sys
import wave
from pathlib import Path


def write_wav(path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(b"\\x00\\x00" * 1000)


parser = argparse.ArgumentParser()
parser.add_argument("--model")
parser.add_argument("--voices-data")
parser.add_argument("--voice-registry")
parser.add_argument("--serve-json", action="store_true")
args = parser.parse_args()
if not args.serve_json:
    raise SystemExit(2)
for line in sys.stdin:
    payload = json.loads(line)
    write_wav(payload["output"])
    print(json.dumps({"ok": True, "sampleRate": 16000}), flush=True)
"""


def _ready_managed_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    wrapper = tmp_path / "fake_kokoro_worker.py"
    wrapper.write_text(FAKE_WORKER_SOURCE, encoding="utf-8")
    model = tmp_path / "kokoro.onnx"
    model.write_bytes(b"model")
    voices_data = tmp_path / "voices.bin"
    voices_data.write_bytes(b"voices")
    registry = tmp_path / "voices.txt"
    registry.write_text("af_heart\n", encoding="utf-8")
    return Path(sys.executable), wrapper, model, voices_data, registry


def test_resident_kokoro_worker_reuses_one_process_and_writes_wav(tmp_path: Path) -> None:
    python, wrapper, model, voices_data, registry = _ready_managed_paths(tmp_path)
    manager = TtsWorkerManager()
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"

    assert manager.synthesize_managed_kokoro(
        python_path=python,
        wrapper_path=wrapper,
        model_path=model,
        voices_data_path=voices_data,
        voice_registry_path=registry,
        text="First line.",
        voice_id="af_heart",
        output=first,
        speed=1.0,
    ) == 16000
    first_status = manager.status(provider="kokoro", setup_mode="managed_onnx")
    assert first_status.state == "running"
    assert first_status.pid

    assert manager.synthesize_managed_kokoro(
        python_path=python,
        wrapper_path=wrapper,
        model_path=model,
        voices_data_path=voices_data,
        voice_registry_path=registry,
        text="Second line.",
        voice_id="af_heart",
        output=second,
        speed=1.2,
    ) == 16000
    second_status = manager.status(provider="kokoro", setup_mode="managed_onnx")

    assert second_status.pid == first_status.pid
    assert second_status.request_count == 2
    with wave.open(str(second), "rb") as audio:
        assert audio.getframerate() == 16000
        assert audio.getnframes() > 0

    manager.stop_all()
    assert manager.status(provider="kokoro", setup_mode="managed_onnx").state == "idle"


class FakeWorkerManager:
    def __init__(self) -> None:
        self.calls = 0

    def synthesize_managed_kokoro(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        output = Path(kwargs["output"])
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(24000)
            target.writeframes(b"\x00\x00" * 1000)
        return 24000


def test_managed_kokoro_adapter_uses_resident_worker_when_injected(tmp_path: Path) -> None:
    python, wrapper, model, voices_data, registry = _ready_managed_paths(tmp_path)
    manager = FakeWorkerManager()
    adapter = ManagedKokoroOnnxAdapter(
        python, wrapper, model, voices_data, registry, manager  # type: ignore[arg-type]
    )

    provenance = adapter.preview(
        "Hello there.",
        "af_heart",
        tmp_path / "adapter.wav",
        DirectionProfile(scopeType="segment", scopeId="seg", pace=1.15),
    )

    assert provenance["workerMode"] == "resident"
    assert provenance["sampleRate"] == 24000
    assert manager.calls == 1


def test_tts_worker_status_endpoint_and_settings_change_stop_worker(
    client, app, tmp_path: Path, monkeypatch
) -> None:
    python, wrapper, model, voices_data, registry = _ready_managed_paths(tmp_path)
    monkeypatch.setattr("echodraft_api.kokoro_setup.write_managed_wrapper", lambda _path: None)

    response = client.put(
        "/api/v1/settings/tts",
        json={
            "provider": "kokoro",
            "setupMode": "managed_onnx",
            "pythonPath": str(python),
            "executable": str(wrapper),
            "modelPath": str(model),
            "voicesDataPath": str(voices_data),
            "voiceRegistryPath": str(registry),
        },
    )
    assert response.status_code == 200
    idle = client.get("/api/v1/settings/tts/worker").json()
    assert idle["workerMode"] == "resident"
    assert idle["state"] == "idle"

    tested = client.post(
        "/api/v1/settings/tts/test",
        json={"text": "Resident worker preview.", "voiceId": "af_heart"},
    )
    assert tested.status_code == 200
    running = client.get("/api/v1/settings/tts/worker").json()
    assert running["state"] == "running"
    assert running["pid"]
    assert running["requestCount"] == 1

    response = client.put("/api/v1/settings/tts", json={"provider": "mock"})
    assert response.status_code == 200
    stopped = app.state.container.tts_worker_manager.status(
        provider="kokoro", setup_mode="managed_onnx"
    )
    assert stopped.state == "idle"
    inactive = client.get("/api/v1/settings/tts/worker").json()
    assert inactive["workerMode"] == "subprocess"
    assert inactive["state"] == "not_applicable"
