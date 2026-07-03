"""R128-style loudness mastering and room-tone generation.

Everything that needs a real audio codec (resampling with a proper anti-alias
filter, EBU R128 loudness measurement, two-pass loudness normalisation, true-peak
limiting) is delegated to ``ffmpeg`` -- already a required system tool for the
export path (``exporting.py`` shells out to it) and the model catalog. Every
ffmpeg invocation is gated on :func:`ffmpeg_available` so a machine without it
degrades honestly (the caller records ``"mastered": false``) instead of crashing
or silently shipping un-mastered audio.

``room_tone`` is pure numpy (no ffmpeg): ACX-style masters reject *digital*
silence at the head/tail, so we lay down a faint pink-ish noise bed at roughly
``-70 dBFS`` RMS instead.

The mastering targets are the plan's named constants (see
``docs/plans/2026-07-04-phase-2-publishable-audio.md``):

* integrated loudness ``I = -19 LUFS``
* true peak ceiling ``TP = -3 dBTP``
* loudness range ``LRA = 11`` (informational target)
* room tone ``1000 ms`` head / ``2000 ms`` tail at ``~ -70 dBFS`` RMS
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

# --- Mastering targets (named constants, per the Phase 2 plan) ---------------------------
TARGET_LUFS = -19.0
TRUE_PEAK_DB = -3.0
TARGET_LRA = 11.0
SAMPLE_RATE = 44_100
FULL_SCALE = 32_768.0

# alimiter's ``limit`` is a linear sample ceiling. -3 dBTP == 10 ** (-3 / 20).
LIMITER_CEILING = round(10 ** (TRUE_PEAK_DB / 20), 4)  # 0.7079

# Room tone: never digital silence at the boundaries.
ROOM_TONE_HEAD_MS = 1000
ROOM_TONE_TAIL_MS = 2000
ROOM_TONE_RMS_DBFS = -70.0

_FFMPEG_TIMEOUT = 600


def ffmpeg_available() -> bool:
    """Whether an ``ffmpeg`` binary is on PATH (the honest-degradation gate)."""
    return shutil.which("ffmpeg") is not None


def resample_command(src: Path, dst: Path, rate: int = SAMPLE_RATE) -> list[str]:
    """ffmpeg argv that resamples ``src`` to mono ``rate`` Hz with the soxr resampler."""
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        "aresample=resampler=soxr",
        "-ar",
        str(rate),
        "-ac",
        "1",
        str(dst),
    ]


def measure_command(src: Path) -> list[str]:
    """ffmpeg argv for the loudnorm first pass (prints measured stats as JSON)."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(src),
        "-af",
        f"loudnorm=I={TARGET_LUFS:g}:TP={TRUE_PEAK_DB:g}:LRA={TARGET_LRA:g}:print_format=json",
        "-f",
        "null",
        "-",
    ]


def master_command(src: Path, dst: Path, measured: dict[str, str]) -> list[str]:
    """ffmpeg argv for the loudnorm second (linear) pass + true-peak limiter.

    ``measured`` threads the first-pass measurements back into loudnorm so the
    second pass applies a single deterministic gain (``linear=true``) instead of
    re-measuring. Values are used verbatim as ffmpeg emitted them.
    """
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        _master_filter(measured),
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        str(dst),
    ]


def _master_filter(measured: dict[str, str]) -> str:
    loudnorm = (
        f"loudnorm=I={TARGET_LUFS:g}:TP={TRUE_PEAK_DB:g}:LRA={TARGET_LRA:g}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        ":linear=true:print_format=summary"
    )
    limiter = f"alimiter=limit={LIMITER_CEILING}:level=false"
    return f"{loudnorm},{limiter}"


def resample_wav(src: Path, dst: Path, rate: int = SAMPLE_RATE) -> None:
    """Resample ``src`` to mono ``rate`` Hz PCM at ``dst`` via ffmpeg soxr."""
    _run(resample_command(src, dst, rate))


def measure_loudness(path: Path) -> dict[str, str]:
    """Run the loudnorm first pass and return its measured statistics.

    Keys include ``input_i`` / ``input_tp`` / ``input_lra`` / ``input_thresh``
    and ``target_offset`` -- exactly the fields the second (linear) pass threads
    back in. Values are the raw strings ffmpeg printed.
    """
    completed = _run(measure_command(path))
    return parse_loudnorm_json(completed.stderr)


def parse_loudnorm_json(stderr: str) -> dict[str, str]:
    """Extract the trailing ``{...}`` loudnorm JSON block ffmpeg writes to stderr."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("loudnorm did not emit a JSON measurement block.")
    payload = json.loads(stderr[start : end + 1])
    return {str(key): str(value) for key, value in payload.items()}


def master_wav(src: Path, dst: Path, measured: dict[str, str]) -> None:
    """Loudness-normalise + true-peak-limit ``src`` into ``dst`` (ffmpeg two-pass)."""
    _run(master_command(src, dst, measured))


def room_tone(duration_ms: int, rate: int = SAMPLE_RATE) -> np.ndarray:
    """Faint pink-ish noise bed (~ -70 dBFS RMS) as int16 mono samples.

    Real (never digital) silence for the head/tail of a master. The spectral tilt
    is produced in the frequency domain (``1/sqrt(f)``) so the whole thing stays
    vectorised -- no per-sample Python loop. Deterministic seed keeps assembled
    renders reproducible.
    """
    count = int(rate * max(0, duration_ms) / 1000)
    if count <= 0:
        return np.zeros(0, dtype=np.int16)
    rng = np.random.default_rng(seed=1729)
    white = rng.standard_normal(count)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(count, d=1.0 / rate)
    tilt = np.ones_like(freqs)
    tilt[1:] = 1.0 / np.sqrt(freqs[1:])
    pink = np.fft.irfft(spectrum * tilt, n=count)
    rms = float(np.sqrt(np.mean(np.square(pink))))
    if rms <= 0:
        return np.zeros(count, dtype=np.int16)
    target_rms = FULL_SCALE * (10 ** (ROOM_TONE_RMS_DBFS / 20))
    scaled = pink * (target_rms / rms)
    return np.clip(np.round(scaled), -32_768, 32_767).astype(np.int16)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=_FFMPEG_TIMEOUT,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            f"ffmpeg failed ({completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed
