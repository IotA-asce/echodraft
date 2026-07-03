import io
import math
import wave

import pytest
from audio_fixtures import wav_bytes, wav_bytes_from_segments
from echodraft_api.audio_analysis import analyze_wav


def _write(tmp_path, name: str, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_known_amplitude_wave_reports_expected_peak_and_rms(tmp_path) -> None:
    # A signal that flips +amplitude/-amplitude every sample has RMS == peak == amplitude
    # exactly, so the expected dBFS values are simple algebra, not empirical guesses.
    amplitude = 16_384
    path = _write(tmp_path, "tone.wav", wav_bytes(amplitude=amplitude, duration_ms=1000))
    analysis = analyze_wav(path)
    expected_dbfs = 20 * math.log10(amplitude / 32768)
    assert analysis.peak_dbfs == pytest.approx(expected_dbfs, abs=0.5)
    assert analysis.rms_dbfs == pytest.approx(expected_dbfs, abs=0.5)
    assert analysis.duration_ms == 1000
    assert analysis.sample_rate == 16_000
    assert analysis.clipped_sample_count == 0


def test_silence_only_file_floors_at_minus_120_dbfs(tmp_path) -> None:
    path = _write(tmp_path, "silence.wav", wav_bytes(amplitude=0, duration_ms=500))
    analysis = analyze_wav(path)
    assert analysis.peak_dbfs == -120.0
    assert analysis.rms_dbfs == -120.0


def test_four_second_mid_file_silence_becomes_one_dead_air_range(tmp_path) -> None:
    data = wav_bytes_from_segments(
        [(16_000, 2000), (0, 4000), (16_000, 2000)], sample_rate=16_000
    )
    path = _write(tmp_path, "gap.wav", data)
    analysis = analyze_wav(path)
    assert analysis.duration_ms == 8000
    assert analysis.dead_air_ranges == [(2000, 6000)]
    # silence_ranges has no minimum-length gate, so it must at least cover the same span.
    assert any(start <= 2000 and end >= 6000 for start, end in analysis.silence_ranges)


def test_head_and_tail_silence_alone_is_not_dead_air(tmp_path) -> None:
    # Room tone at the very start/end of a file is legitimate and must not be flagged as
    # dead air; only a sustained run strictly inside the file counts.
    data = wav_bytes_from_segments([(0, 4000), (16_000, 1000), (0, 4000)], sample_rate=16_000)
    path = _write(tmp_path, "headtail.wav", data)
    analysis = analyze_wav(path)
    assert analysis.dead_air_ranges == []


def test_clipped_samples_are_counted(tmp_path) -> None:
    data = wav_bytes_from_segments([(32_760, 100)], sample_rate=16_000)
    path = _write(tmp_path, "clip.wav", data)
    analysis = analyze_wav(path)
    expected_frames = int(16_000 * 100 / 1000)
    assert analysis.clipped_sample_count == expected_frames


def test_waveform_peaks_has_200_buckets_and_normalizes_near_one(tmp_path) -> None:
    data = wav_bytes_from_segments([(32_760, 500)], sample_rate=16_000)
    path = _write(tmp_path, "loud.wav", data)
    analysis = analyze_wav(path)
    assert len(analysis.waveform_peaks) == 200
    assert max(analysis.waveform_peaks) == pytest.approx(1.0, abs=0.02)
    assert min(analysis.waveform_peaks) >= 0.0


def test_empty_file_does_not_crash(tmp_path) -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(b"")
    path = _write(tmp_path, "empty.wav", buffer.getvalue())
    analysis = analyze_wav(path)
    assert analysis.duration_ms == 0
    assert analysis.peak_dbfs == -120.0
    assert analysis.rms_dbfs == -120.0
    assert analysis.dead_air_ranges == []
    assert analysis.silence_ranges == []
    assert len(analysis.waveform_peaks) == 200
    assert analysis.clipped_sample_count == 0


def test_single_sample_file_does_not_crash(tmp_path) -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes((20_000).to_bytes(2, "little", signed=True))
    path = _write(tmp_path, "one-sample.wav", buffer.getvalue())
    analysis = analyze_wav(path)
    assert len(analysis.waveform_peaks) == 200
    assert analysis.peak_dbfs > -120.0


def test_eight_bit_pcm_is_decoded_gracefully(tmp_path) -> None:
    amplitude = 100
    data = wav_bytes_from_segments(
        [(amplitude, 200)], sample_rate=16_000, sample_width=1
    )
    path = _write(tmp_path, "eight-bit.wav", data)
    analysis = analyze_wav(path)
    # 8-bit samples are scaled onto the 16-bit range via (value - 128) * 256 before
    # measurement, so the expected dBFS is computable from that documented scaling.
    expected_dbfs = 20 * math.log10((amplitude * 256) / 32768)
    assert analysis.peak_dbfs == pytest.approx(expected_dbfs, abs=0.5)


def test_thirtytwo_bit_pcm_is_decoded_gracefully(tmp_path) -> None:
    amplitude = 1_000_000_000
    data = wav_bytes_from_segments(
        [(amplitude, 200)], sample_rate=16_000, sample_width=4
    )
    path = _write(tmp_path, "thirtytwo-bit.wav", data)
    analysis = analyze_wav(path)
    expected_dbfs = 20 * math.log10((amplitude // 65536) / 32768)
    assert analysis.peak_dbfs == pytest.approx(expected_dbfs, abs=0.5)


def test_multichannel_file_is_downmixed_without_crashing(tmp_path) -> None:
    data = wav_bytes_from_segments(
        [(20_000, 500)], sample_rate=16_000, channels=2
    )
    path = _write(tmp_path, "stereo.wav", data)
    analysis = analyze_wav(path)
    assert analysis.duration_ms == 500
    assert analysis.peak_dbfs > -120.0
    assert len(analysis.waveform_peaks) == 200
    # Both channels carry identical content, so clipping is counted per channel-sample.
    assert analysis.clipped_sample_count == 0

