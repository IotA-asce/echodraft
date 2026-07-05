from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .config import AppSettings
from .system_tools import resolve_system_tool

ASR_MATCH_THRESHOLD = 0.90
ASR_MIN_TOKENS = 4


@dataclass(frozen=True)
class WordMatchResult:
    status: str
    match_ratio: float
    word_error_rate: float
    expected_word_count: int
    transcript_word_count: int
    edit_distance: int
    missing_words: list[str]
    extra_words: list[str]


@dataclass(frozen=True)
class AsrVerificationResult:
    status: str
    provider: str
    model: str | None
    transcript: str
    evidence: dict[str, object]
    error: str | None = None


def score_word_match(expected: str, transcript: str) -> WordMatchResult:
    expected_words = _words(expected)
    transcript_words = _words(transcript)
    if len(expected_words) < ASR_MIN_TOKENS:
        return WordMatchResult(
            status="skipped_short_text",
            match_ratio=1.0,
            word_error_rate=0.0,
            expected_word_count=len(expected_words),
            transcript_word_count=len(transcript_words),
            edit_distance=0,
            missing_words=[],
            extra_words=[],
        )
    distance = _edit_distance(expected_words, transcript_words)
    word_error_rate = distance / len(expected_words)
    match_ratio = max(0.0, 1.0 - word_error_rate)
    status = "passed" if match_ratio >= ASR_MATCH_THRESHOLD else "failed"
    return WordMatchResult(
        status=status,
        match_ratio=round(match_ratio, 4),
        word_error_rate=round(word_error_rate, 4),
        expected_word_count=len(expected_words),
        transcript_word_count=len(transcript_words),
        edit_distance=distance,
        missing_words=_sample_missing_words(expected_words, transcript_words),
        extra_words=_sample_missing_words(transcript_words, expected_words),
    )


class LocalAsrVerifier:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def configured(self) -> bool:
        return bool(self._executable() and self.settings.asr_model_path)

    def verify(self, audio_path: Path, expected_text: str, output_root: Path) -> AsrVerificationResult:
        if not expected_text.strip():
            return self._result("skipped_empty_text", None, "", score_word_match("", ""))
        executable = self._executable()
        if not executable or not self.settings.asr_model_path:
            return AsrVerificationResult(
                status="skipped_unconfigured",
                provider="whisper.cpp",
                model=str(self.settings.asr_model_path) if self.settings.asr_model_path else None,
                transcript="",
                evidence={
                    "reason": "asr_unconfigured",
                    "provider": "whisper.cpp",
                    "configured": False,
                },
            )
        output_root.mkdir(parents=True, exist_ok=True)
        output_prefix = output_root / f"asr_{uuid4().hex[:12]}"
        command = [
            executable,
            "-m",
            str(self.settings.asr_model_path),
            "-f",
            str(audio_path),
            "-oj",
            "-of",
            str(output_prefix),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            return self._error(str(error), expected_text, model_path=self.settings.asr_model_path)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "ASR process failed.").strip()
            return self._error(message[:500], expected_text, model_path=self.settings.asr_model_path)
        json_path = output_prefix.with_suffix(".json")
        try:
            transcript = transcript_from_whisper_json(json.loads(json_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            return self._error(f"ASR JSON output could not be read: {error}", expected_text, model_path=self.settings.asr_model_path)
        return self._result(
            "whisper.cpp",
            self.settings.asr_model_path,
            transcript,
            score_word_match(expected_text, transcript),
            expected_text=expected_text,
        )

    def _executable(self) -> str | None:
        if self.settings.asr_executable:
            return self.settings.asr_executable
        return resolve_system_tool("whisper-cli")

    @staticmethod
    def _result(
        provider: str | None,
        model_path: Path | None,
        transcript: str,
        score: WordMatchResult,
        *,
        expected_text: str = "",
    ) -> AsrVerificationResult:
        evidence = {
            "reason": "asr_word_match",
            "provider": provider or "whisper.cpp",
            "status": score.status,
            "matchRatio": score.match_ratio,
            "wordErrorRate": score.word_error_rate,
            "expectedWordCount": score.expected_word_count,
            "transcriptWordCount": score.transcript_word_count,
            "editDistance": score.edit_distance,
            "missingWords": score.missing_words,
            "extraWords": score.extra_words,
            "expectedPreview": expected_text[:240],
            "transcriptPreview": transcript[:240],
            "model": model_path.name if model_path else None,
        }
        return AsrVerificationResult(
            status=score.status,
            provider=provider or "whisper.cpp",
            model=model_path.name if model_path else None,
            transcript=transcript,
            evidence=evidence,
        )

    @staticmethod
    def _error(error: str, expected_text: str, *, model_path: Path | None) -> AsrVerificationResult:
        score = score_word_match(expected_text, "")
        evidence = {
            **LocalAsrVerifier._result(
                "whisper.cpp", model_path, "", score, expected_text=expected_text
            ).evidence,
            "reason": "asr_verification_error",
            "error": error[:500],
        }
        return AsrVerificationResult(
            status="error",
            provider="whisper.cpp",
            model=model_path.name if model_path else None,
            transcript="",
            evidence=evidence,
            error=error[:500],
        )


def transcript_from_whisper_json(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Whisper JSON output is not an object.")
    transcription = payload.get("transcription")
    if isinstance(transcription, list):
        parts = [
            str(item.get("text") or "")
            for item in transcription
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        ]
        if parts:
            return " ".join(parts).strip()
    result = payload.get("result")
    if isinstance(result, dict):
        result_text = result.get("text")
        if isinstance(result_text, str):
            return result_text.strip()
    text = payload.get("text")
    if isinstance(text, str):
        return text.strip()
    raise ValueError("Whisper JSON output does not contain transcript text.")


def _words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", value.casefold())


def _edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_word in enumerate(left, 1):
        current = [left_index]
        for right_index, right_word in enumerate(right, 1):
            current.append(
                min(
                    current[right_index - 1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_word != right_word),
                )
            )
        previous = current
    return previous[-1]


def _sample_missing_words(source: list[str], comparison: list[str]) -> list[str]:
    remaining = comparison.copy()
    missing: list[str] = []
    for word in source:
        try:
            remaining.remove(word)
        except ValueError:
            if word not in missing:
                missing.append(word)
        if len(missing) >= 10:
            break
    return missing
