import math
import struct
import time
import wave
from pathlib import Path

from echodraft_api.voice_catalog import VoiceCatalogService, measure_wav


def _wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def _write_sine_sweep(
    path: Path,
    *,
    start_hz: float = 150.0,
    end_hz: float = 250.0,
    duration: float = 2.0,
    sample_rate: int = 24000,
    amplitude: float = 0.6,
) -> None:
    """Synthesize a linear sine-sweep WAV so pitch tracking can be verified
    against a known, non-constant frequency band (a fabricated +/-10% band
    around a single average could never reproduce this asymmetric range)."""
    frame_count = int(duration * sample_rate)
    samples: list[int] = []
    phase = 0.0
    for index in range(frame_count):
        t = index / sample_rate
        instantaneous_hz = start_hz + (end_hz - start_hz) * (t / duration)
        phase += 2 * math.pi * instantaneous_hz / sample_rate
        samples.append(int(amplitude * 32767 * math.sin(phase)))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def test_audition_backfill_measures_and_links_voice_catalog(client) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"title": "Voice catalog", "rightsStatus": "declared"},
    ).json()["id"]
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={
            "name": "Measured narrator",
            "backend": "mock",
            "providerVoiceId": "mock-narrator",
        },
    ).json()
    assert voice["voiceCatalogEntryId"] is None

    job = client.post("/api/v1/voice-catalog/audition-jobs").json()
    assert _wait_for_job(client, job["id"])["status"] == "succeeded"

    catalog = client.get("/api/v1/voice-catalog").json()
    assert {entry["engineVoiceId"] for entry in catalog} == {
        "mock-narrator",
        "mock-character",
    }
    narrator = next(
        entry for entry in catalog if entry["engineVoiceId"] == "mock-narrator"
    )
    assert narrator["labeledBy"]["method"] == "local_acoustic_measurement"
    assert narrator["acoustics"]["sampleRate"] == 16000
    # Fabricated fields are gone entirely rather than faked; loudness is
    # honestly named for what it is (RMS dBFS), not mislabeled as "shimmer".
    assert "jitterPercent" not in narrator["acoustics"]
    assert "shimmerPercent" not in narrator["acoustics"]
    assert "rmsDbfs" in narrator["acoustics"]
    assert Path(narrator["samplePaths"]["auditionWav"]).is_file()

    refreshed = client.get(f"/api/v1/projects/{project}/voices").json()[0]
    assert refreshed["voiceCatalogEntryId"] == narrator["id"]
    assert refreshed["facets"] == narrator["facets"]

    rerun = client.post("/api/v1/voice-catalog/audition-jobs").json()
    assert _wait_for_job(client, rerun["id"])["status"] == "succeeded"
    assert len(client.get("/api/v1/voice-catalog").json()) == 2


def test_audition_backfill_is_incremental_unless_forced(client) -> None:
    """A voice already cataloged for the same (engine, engineVersion,
    engineVoiceId) is skipped on rerun -- no re-synthesis -- unless
    ``force=True`` is passed explicitly."""
    container = client.app.state.container
    calls: list[str] = []
    original_preview = container.tts_adapter.preview

    def counting_preview(text, voice_id, output, direction):
        calls.append(voice_id)
        return original_preview(text, voice_id, output, direction)

    container.tts_adapter.preview = counting_preview  # type: ignore[method-assign]
    service = VoiceCatalogService(container)

    first = service.audition_backfill()
    assert len(first) == 2
    assert sorted(calls) == ["mock-character", "mock-narrator"]

    calls.clear()
    second = service.audition_backfill()
    assert len(second) == 2
    assert calls == []  # both already cataloged: nothing re-synthesized

    third = service.audition_backfill(force=True)
    assert len(third) == 2
    assert sorted(calls) == ["mock-character", "mock-narrator"]


def test_measure_wav_detects_real_pitch_and_omits_fabricated_fields(tmp_path: Path) -> None:
    """Pitch comes from real autocorrelation over a synthesized sine-sweep WAV
    with a known, asymmetric [150Hz, 250Hz] band -- a fabricated +/-10% band
    around a single average could never reproduce this. jitter/shimmer are
    absent entirely (never measured, so never faked); loudness is honestly
    named `rmsDbfs`."""
    wav_path = tmp_path / "sweep.wav"
    _write_sine_sweep(wav_path, start_hz=150.0, end_hz=250.0, duration=2.0)

    acoustics = measure_wav(wav_path, word_count=10)

    assert "jitterPercent" not in acoustics
    assert "shimmerPercent" not in acoustics
    assert "rmsDbfs" in acoustics
    assert acoustics["rmsDbfs"] < 0.0

    pitch_median = acoustics["pitchMedianHz"]
    low, high = acoustics["pitchRangeHz"]
    assert 180.0 <= pitch_median <= 220.0
    assert 130.0 <= low < pitch_median
    assert pitch_median < high <= 270.0

    assert 0.0 <= acoustics["spectralBrightness"] <= 1.0


def test_measure_wav_reports_silence_honestly_without_crashing(tmp_path: Path) -> None:
    """All-silence audio (e.g. the mock TTS adapter's placeholder frames)
    must never crash and must never fabricate a pitch/brightness reading."""
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)

    acoustics = measure_wav(wav_path, word_count=5)

    assert acoustics["pitchMedianHz"] == 0.0
    assert acoustics["pitchRangeHz"] == [0.0, 0.0]
    assert acoustics["spectralBrightness"] == 0.0
    assert acoustics["rmsDbfs"] < -60.0
