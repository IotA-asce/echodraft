"""Shared WAV fabrication helpers for tests.

These build small, deterministic PCM WAV files in memory (no real codec, no ffmpeg) so
audio-analysis and QA-rule tests can assert exact expected peak/RMS/duration values.
"""

import io
import struct
import wave


def wav_bytes(amplitude: int = 4000, duration_ms: int = 600, sample_rate: int = 16_000) -> bytes:
    """A mono 16-bit PCM WAV of alternating +amplitude/-amplitude samples.

    Flipping sign every sample keeps RMS == peak == amplitude exactly (no duty-cycle
    math needed), which makes expected dB values trivial to compute in tests.
    """
    return wav_bytes_from_segments([(amplitude, duration_ms)], sample_rate=sample_rate)


def wav_bytes_from_segments(
    segments: list[tuple[int, int]],
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Fabricate a WAV by concatenating (amplitude, duration_ms) segments.

    Each segment alternates +amplitude/-amplitude per sample (amplitude == 0 yields
    digital silence for that span). ``amplitude`` is expressed in the *native* range for
    ``sample_width`` (e.g. -128..127 for 8-bit, -32768..32767 for 16-bit). The same value
    is written to every channel.
    """
    samples: list[int] = []
    for amplitude, duration_ms in segments:
        frames = int(sample_rate * duration_ms / 1000)
        for index in range(frames):
            value = amplitude if index % 2 == 0 else -amplitude
            samples.extend([value] * channels)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(sample_rate)
        target.writeframes(_pack_samples(samples, sample_width))
    return buffer.getvalue()


def _pack_samples(samples: list[int], width: int) -> bytes:
    if width == 1:
        return struct.pack(f"<{len(samples)}B", *[max(0, min(255, value + 128)) for value in samples])
    if width == 2:
        return struct.pack(f"<{len(samples)}h", *samples)
    if width == 3:
        packed = bytearray()
        for value in samples:
            packed.extend(int(value).to_bytes(3, byteorder="little", signed=True))
        return bytes(packed)
    if width == 4:
        return struct.pack(f"<{len(samples)}i", *samples)
    raise ValueError(f"Unsupported sample width for test fixture: {width}")
