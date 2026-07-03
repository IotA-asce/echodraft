"""Real (non-faked) WAV analysis shared by rendering, assembly, review, and readiness.

Everything here is stdlib ``wave`` + numpy on PCM frames already on disk -- no ffmpeg, no
network, no external services, so it runs the same in CI as on a laptop.

Sample-width handling: PCM WAVs are only ever 1, 2, 3, or 4 bytes/sample. Every width is
scaled onto a common 16-bit-equivalent integer range before measurement, so peak/RMS/
clipping math is a single code path regardless of source width:
  - 1 byte (unsigned):  ``(value - 128) * 256``
  - 2 bytes (signed):   used as-is (the native, fully-precise case)
  - 3 bytes (signed):   sign-extended, then floor-divided by 256
  - 4 bytes (signed):   floor-divided by 65536
Any other width is not valid PCM and raises ``ValueError`` (surfaced by callers as a
"corrupt audio" finding, same as an unreadable WAV container).

Multi-channel files are downmixed to mono (mean across channels) for the time-ordered
measurements (dead air, silence ranges, waveform buckets), since those care about *when*
something happens, not which channel it happened on. Peak/RMS/clipping are measured on the
raw interleaved samples (order-independent whole-file aggregates), so a signal that is loud
on only one channel of a stereo file is never averaged away.
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FULL_SCALE = 32768.0
FLOOR_DBFS = -120.0
CLIP_THRESHOLD = 32_760
WAVEFORM_BUCKETS = 200
WINDOW_MS = 500
DEAD_AIR_MIN_RUN_MS = 3000
DEAD_AIR_THRESHOLD_DBFS = -60.0

_SUPPORTED_WIDTHS = {1, 2, 3, 4}


@dataclass(frozen=True)
class AudioAnalysis:
    """Measurements computed once per WAV and reused by every QA/readiness consumer."""

    peak_dbfs: float
    rms_dbfs: float
    dead_air_ranges: list[tuple[int, int]]
    waveform_peaks: list[float]
    silence_ranges: list[tuple[int, int]]
    duration_ms: int
    sample_rate: int
    clipped_sample_count: int


def analyze_wav(path: Path) -> AudioAnalysis:
    """Decode a PCM WAV and compute honest loudness/silence/waveform metrics.

    Raises the same exceptions ``wave.open``/``readframes`` would (``wave.Error``,
    ``EOFError``) for a corrupt/unreadable container, and ``ValueError`` for a sample
    width that is not valid PCM (1/2/3/4 bytes) -- callers already treat "cannot decode
    this WAV" as a single case and should catch all three the same way.
    """
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        n_frames = source.getnframes()
        raw = source.readframes(n_frames)

    duration_ms = int(n_frames / rate * 1000) if rate else 0
    flat = _decode_pcm(raw, width) if raw else np.array([], dtype=np.int64)

    if flat.size == 0:
        return AudioAnalysis(
            peak_dbfs=FLOOR_DBFS,
            rms_dbfs=FLOOR_DBFS,
            dead_air_ranges=[],
            waveform_peaks=[0.0] * WAVEFORM_BUCKETS,
            silence_ranges=[],
            duration_ms=duration_ms,
            sample_rate=rate,
            clipped_sample_count=0,
        )

    flat_f = flat.astype(np.float64)
    peak = float(np.max(np.abs(flat_f)))
    rms = float(np.sqrt(np.mean(np.square(flat_f))))
    clipped_sample_count = int(np.count_nonzero(np.abs(flat) >= CLIP_THRESHOLD))

    if channels > 1:
        usable = (flat_f.size // channels) * channels
        mono = flat_f[:usable].reshape(-1, channels).mean(axis=1)
    else:
        mono = flat_f

    dead_air_ranges, silence_ranges = _silence_windows(mono, rate, duration_ms)
    waveform_peaks = _bucket_peaks(mono)

    return AudioAnalysis(
        peak_dbfs=_to_dbfs(peak),
        rms_dbfs=_to_dbfs(rms),
        dead_air_ranges=dead_air_ranges,
        waveform_peaks=waveform_peaks,
        silence_ranges=silence_ranges,
        duration_ms=duration_ms,
        sample_rate=rate,
        clipped_sample_count=clipped_sample_count,
    )


def _decode_pcm(raw: bytes, width: int) -> np.ndarray:
    if width not in _SUPPORTED_WIDTHS:
        raise ValueError(f"Unsupported WAV sample width: {width} bytes.")
    if width == 1:
        values = np.frombuffer(raw, dtype=np.uint8).astype(np.int32)
        return (values - 128) * 256
    if width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.int32)
    if width == 4:
        values64 = np.frombuffer(raw, dtype="<i4").astype(np.int64)
        return values64 // 65536
    # width == 3: no native numpy dtype for 24-bit PCM; unpack the byte triples by hand.
    usable_len = len(raw) - (len(raw) % 3)
    as_bytes = np.frombuffer(raw[:usable_len], dtype=np.uint8).reshape(-1, 3)
    values = (
        as_bytes[:, 0].astype(np.int32)
        | (as_bytes[:, 1].astype(np.int32) << 8)
        | (as_bytes[:, 2].astype(np.int32) << 16)
    )
    values = np.where(values >= (1 << 23), values - (1 << 24), values)
    return values // 256


def _to_dbfs(value: float) -> float:
    if value <= 0:
        return FLOOR_DBFS
    return max(20.0 * math.log10(value / FULL_SCALE), FLOOR_DBFS)


def _bucket_peaks(mono: np.ndarray) -> list[float]:
    if mono.size == 0:
        return [0.0] * WAVEFORM_BUCKETS
    magnitude = np.abs(mono)
    chunks = np.array_split(magnitude, WAVEFORM_BUCKETS)
    peaks = []
    for chunk in chunks:
        value = float(chunk.max()) / FULL_SCALE if chunk.size else 0.0
        peaks.append(min(1.0, max(0.0, value)))
    return peaks


def _window_rms(mono: np.ndarray, window_samples: int) -> np.ndarray:
    n_full = mono.size // window_samples
    remainder = mono.size % window_samples
    parts: list[np.ndarray] = []
    if n_full:
        full = mono[: n_full * window_samples].reshape(n_full, window_samples)
        parts.append(np.sqrt(np.mean(np.square(full), axis=1)))
    if remainder:
        tail = mono[n_full * window_samples :]
        parts.append(np.array([np.sqrt(np.mean(np.square(tail)))]))
    return np.concatenate(parts) if parts else np.array([])


def _merge_runs(bounds: list[tuple[int, int]], flags: list[bool]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    run_start: int | None = None
    run_end = 0
    for (start, end), flag in zip(bounds, flags):
        if flag:
            if run_start is None:
                run_start = start
            run_end = end
        elif run_start is not None:
            ranges.append((run_start, run_end))
            run_start = None
    if run_start is not None:
        ranges.append((run_start, run_end))
    return ranges


def _silence_windows(
    mono: np.ndarray, rate: int, duration_ms: int
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    if rate <= 0 or mono.size == 0:
        return [], []
    window_samples = max(1, round(rate * WINDOW_MS / 1000))
    rms_per_window = _window_rms(mono, window_samples)
    n_windows = len(rms_per_window)
    bounds = [
        (index * WINDOW_MS, min((index + 1) * WINDOW_MS, duration_ms)) for index in range(n_windows)
    ]
    is_silent = [_to_dbfs(float(value)) < DEAD_AIR_THRESHOLD_DBFS for value in rms_per_window]

    silence_ranges = _merge_runs(bounds, is_silent)

    # Head/tail room tone is legitimate: any silent run touching the very start or very end
    # of the file is excluded wholesale (however long), not just its outermost window. Only
    # a run strictly inside the file -- with real audio on both sides -- can be "dead air".
    dead_air_ranges = [
        (start, end)
        for start, end in silence_ranges
        if start > 0 and end < duration_ms and (end - start) >= DEAD_AIR_MIN_RUN_MS
    ]
    return dead_air_ranges, silence_ranges
