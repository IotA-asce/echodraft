"""Mastering module: ffmpeg command construction (monkeypatched) + skipif integration."""

from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from echodraft_api import mastering
from echodraft_api.audio_analysis import analyze_wav

MEASURED = {
    "input_i": "-30.12",
    "input_tp": "-5.40",
    "input_lra": "7.10",
    "input_thresh": "-40.30",
    "target_offset": "0.55",
}


def test_resample_command_uses_soxr_and_target_rate() -> None:
    command = mastering.resample_command(Path("in.wav"), Path("out.wav"))
    assert command[0] == "ffmpeg"
    assert command[command.index("-af") + 1] == "aresample=resampler=soxr"
    assert command[command.index("-ar") + 1] == "44100"
    assert command[command.index("-ac") + 1] == "1"
    assert command[-1] == "out.wav"


def test_measure_command_requests_json_loudnorm_first_pass() -> None:
    command = mastering.measure_command(Path("in.wav"))
    filter_arg = command[command.index("-af") + 1]
    assert filter_arg == "loudnorm=I=-19:TP=-3:LRA=11:print_format=json"
    assert command[-1] == "-"
    assert "null" in command


def test_master_command_threads_measured_values_and_limits_true_peak() -> None:
    command = mastering.master_command(Path("in.wav"), Path("out.wav"), MEASURED)
    filter_arg = command[command.index("-af") + 1]
    loudnorm, limiter = filter_arg.split(",")
    assert loudnorm.startswith("loudnorm=I=-19:TP=-3:LRA=11")
    assert ":measured_I=-30.12" in loudnorm
    assert ":measured_TP=-5.40" in loudnorm
    assert ":measured_LRA=7.10" in loudnorm
    assert ":measured_thresh=-40.30" in loudnorm
    assert ":offset=0.55" in loudnorm
    assert ":linear=true" in loudnorm
    # -3 dBTP == 0.7079 linear ceiling; level compensation off so it only limits peaks.
    assert limiter == "alimiter=limit=0.7079:level=false"
    assert command[command.index("-ar") + 1] == "44100"


def test_measure_loudness_parses_trailing_json_block(monkeypatch) -> None:
    stderr = (
        "ffmpeg version ...\n"
        "[Parsed_loudnorm_0 @ 0x0] \n"
        "{\n"
        '\t"input_i" : "-30.12",\n'
        '\t"input_tp" : "-5.40",\n'
        '\t"input_lra" : "7.10",\n'
        '\t"input_thresh" : "-40.30",\n'
        '\t"target_offset" : "0.55"\n'
        "}\n"
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)

    monkeypatch.setattr(mastering.subprocess, "run", fake_run)
    measured = mastering.measure_loudness(Path("in.wav"))
    assert measured["input_i"] == "-30.12"
    assert measured["target_offset"] == "0.55"


def test_ffmpeg_failure_raises_value_error(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(mastering.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="ffmpeg failed"):
        mastering.resample_wav(Path("in.wav"), Path("out.wav"))


def test_room_tone_is_faint_noise_not_digital_silence() -> None:
    samples = mastering.room_tone(1000, rate=44_100)
    assert samples.dtype == np.int16
    assert samples.size == 44_100
    # Not digital silence: some non-zero energy is present.
    assert int(np.count_nonzero(samples)) > 0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    rms_dbfs = 20 * np.log10(rms / 32768.0)
    # Around -70 dBFS RMS (loose tolerance for the noise realisation + rounding).
    assert -80.0 < rms_dbfs < -60.0


def test_room_tone_zero_duration_is_empty() -> None:
    assert mastering.room_tone(0).size == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_master_wav_hits_loudness_target(tmp_path: Path) -> None:
    # A quiet -30 dBFS-ish 200 Hz tone; mastering should lift it toward -19 LUFS.
    rate = 44_100
    duration_s = 8
    t = np.arange(rate * duration_s) / rate
    amplitude = int(32768 * (10 ** (-30 / 20)))
    tone = (np.sin(2 * np.pi * 200 * t) * amplitude).astype(np.int16)
    src = tmp_path / "src.wav"
    with wave.open(str(src), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(struct.pack(f"<{tone.size}h", *tone.tolist()))

    measured = mastering.measure_loudness(src)
    dst = tmp_path / "mastered.wav"
    mastering.master_wav(src, dst, measured)
    assert dst.is_file()

    remeasured = mastering.measure_loudness(dst)
    integrated = float(remeasured["input_i"])
    true_peak = float(remeasured["input_tp"])
    assert abs(integrated - mastering.TARGET_LUFS) <= 1.5
    assert true_peak <= mastering.TRUE_PEAK_DB + 0.5
    assert analyze_wav(dst).sample_rate == rate
