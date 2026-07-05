from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from audio_fixtures import wav_bytes
from echodraft_api import asr_verification
from echodraft_api.asr_verification import (
    LocalAsrVerifier,
    score_word_match,
    transcript_from_whisper_json,
)
from echodraft_api.config import AppSettings


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        artifact_root=tmp_path / "artifacts",
        asr_executable="/usr/local/bin/whisper-cli",
        asr_model_path=tmp_path / "ggml-base.en.bin",
    )


def test_word_match_scores_exact_text_with_normalization() -> None:
    result = score_word_match("Hello, brave world!", "hello brave world")

    assert result.status == "skipped_short_text"
    assert result.match_ratio == 1.0


def test_word_match_scores_pass_and_fail_cases() -> None:
    passed = score_word_match(
        "The signal is fading beyond the ridge tonight.",
        "the signal is fading beyond the ridge tonight",
    )
    failed = score_word_match(
        "The signal is fading beyond the ridge tonight.",
        "the kettle is ringing under the bridge",
    )

    assert passed.status == "passed"
    assert passed.match_ratio == 1.0
    assert failed.status == "failed"
    assert failed.match_ratio < 0.9
    assert "signal" in failed.missing_words
    assert "kettle" in failed.extra_words


def test_transcript_from_whisper_json_accepts_common_shapes() -> None:
    assert (
        transcript_from_whisper_json(
            {"transcription": [{"text": " first"}, {"text": "second "}]}
        )
        == "first second"
    )
    assert transcript_from_whisper_json({"result": {"text": "result text"}}) == "result text"
    assert transcript_from_whisper_json({"text": "plain text"}) == "plain text"


def test_whisper_cli_adapter_writes_json_and_returns_evidence(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(wav_bytes(duration_ms=300))
    model = tmp_path / "ggml-base.en.bin"
    model.write_text("fake", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        output_prefix = Path(command[command.index("-of") + 1])
        output_prefix.with_suffix(".json").write_text(
            '{"transcription":[{"text":"The signal is fading beyond the ridge tonight."}]}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(asr_verification.subprocess, "run", fake_run)
    verifier = LocalAsrVerifier(settings(tmp_path))

    result = verifier.verify(
        audio,
        "The signal is fading beyond the ridge tonight.",
        tmp_path / "asr",
    )

    assert result.status == "passed"
    assert result.evidence["matchRatio"] == 1.0
    assert commands
    assert commands[0][:5] == ["/usr/local/bin/whisper-cli", "-m", str(model), "-f", str(audio)]
    assert "-oj" in commands[0]


def test_whisper_cli_adapter_fails_closed_on_process_error(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "speech.wav"
    audio.write_bytes(wav_bytes(duration_ms=300))

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="model failed")

    monkeypatch.setattr(asr_verification.subprocess, "run", fake_run)

    result = LocalAsrVerifier(settings(tmp_path)).verify(
        audio,
        "The signal is fading beyond the ridge tonight.",
        tmp_path / "asr",
    )

    assert result.status == "error"
    assert result.evidence["reason"] == "asr_verification_error"
    assert "model failed" in str(result.evidence["error"])
