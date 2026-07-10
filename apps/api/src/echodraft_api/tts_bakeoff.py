from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from .audio_analysis import analyze_wav
from .orchestrator import HardwareSnapshot, tts_device


@dataclass(frozen=True)
class Candidate:
    id: str
    display_name: str
    import_name: str
    license: str
    license_gate: str
    source_url: str
    model_card_url: str
    consent_required: bool = True


@dataclass(frozen=True)
class BakeoffScript:
    id: str
    label: str
    text: str
    direction: dict[str, object]


CANDIDATES = (
    Candidate(
        id="chatterbox",
        display_name="Chatterbox",
        import_name="chatterbox",
        license="MIT",
        license_gate="pass",
        source_url="https://github.com/resemble-ai/chatterbox",
        model_card_url="https://huggingface.co/ResembleAI/chatterbox",
    ),
    Candidate(
        id="zonos",
        display_name="Zonos v0.1",
        import_name="zonos",
        license="Apache-2.0",
        license_gate="pass",
        source_url="https://github.com/Zyphra/Zonos",
        model_card_url="https://huggingface.co/Zyphra/Zonos-v0.1-transformer",
    ),
    Candidate(
        id="orpheus",
        display_name="Orpheus 3B",
        import_name="orpheus_tts",
        license="Apache-2.0 model card; Llama-base terms require ledger review",
        license_gate="conditional",
        source_url="https://github.com/canopyai/Orpheus-TTS",
        model_card_url="https://huggingface.co/canopylabs/orpheus-3b-0.1-pretrained",
    ),
)


def fixed_corpus() -> list[BakeoffScript]:
    neutral = (
        "At first light, the station clock opened its pale face above the empty platform. "
        "Mara checked the folded map, listened to the rails settle, and waited without speaking. "
        "Beyond the roof, rain moved across the fields in silver bands. "
    )
    long_text = " ".join(f"Passage {index}. {neutral}" for index in range(1, 41))
    return [
        BakeoffScript("neutral", "Neutral narration", neutral * 13, {"emotion": "neutral"}),
        BakeoffScript(
            "angry", "Angry outburst", "Stop. You knew the bridge was unsafe, and you sent them anyway!", {"emotion": "angry", "intensity": 0.9}
        ),
        BakeoffScript(
            "whisper", "Whisper", "Keep your voice down. Someone is waiting beyond that door.", {"emotion": "quiet", "whisper": True}
        ),
        BakeoffScript(
            "laughter", "Authored laughter", "He laughed, briefly and without cruelty, before answering her question.", {"emotion": "bright"}
        ),
        BakeoffScript(
            "grief", "Grief and anguish", "She released a slow sigh. Nothing in the silent room could bring him home.", {"emotion": "somber", "pace": 0.8}
        ),
        BakeoffScript(
            "long_stability", "Long paragraph stability", long_text, {"emotion": "neutral"}
        ),
        BakeoffScript(
            "multi_character", "Multi-character contrast", "Mara refused. Theo warned her. The guard answered with a clipped command.", {"voices": 3}
        ),
        BakeoffScript(
            "pronunciation", "Pronunciation", "Ilyrien read the minute record, then examined the wind-bound minute hand.", {"pronunciations": ["Ilyrien"]}
        ),
    ]


def preflight(hardware: HardwareSnapshot) -> dict[str, object]:
    return {
        "hardware": {
            **asdict(hardware),
            "ttsDevice": tts_device(hardware),
        },
        "corpus": [
            {
                "id": script.id,
                "label": script.label,
                "wordCount": len(script.text.split()),
            }
            for script in fixed_corpus()
        ],
        "candidates": [
            {
                **asdict(candidate),
                "runtimeInstalled": importlib.util.find_spec(candidate.import_name) is not None,
                "eligibleForExecution": (
                    importlib.util.find_spec(candidate.import_name) is not None
                    and candidate.license_gate == "pass"
                ),
            }
            for candidate in CANDIDATES
        ],
    }


def measure_render(
    path: Path,
    *,
    wall_clock_seconds: float,
    asr_word_error_rate: float | None,
) -> dict[str, object]:
    analysis = analyze_wav(path)
    duration_seconds = analysis.duration_ms / 1000
    silence_ms = sum(end - start for start, end in analysis.silence_ranges)
    silence_ratio = silence_ms / analysis.duration_ms if analysis.duration_ms else 1.0
    rtf = wall_clock_seconds / duration_seconds if duration_seconds else None
    stability_pass = bool(
        analysis.duration_ms > 0
        and silence_ratio < 0.35
        and analysis.clipped_sample_count == 0
        and (asr_word_error_rate is None or asr_word_error_rate <= 0.10)
    )
    return {
        "audioPath": str(path),
        "wallClockSeconds": round(wall_clock_seconds, 4),
        "durationSeconds": round(duration_seconds, 4),
        "rtf": round(rtf, 4) if rtf is not None else None,
        "rmsDbfs": round(analysis.rms_dbfs, 3),
        "peakDbfs": round(analysis.peak_dbfs, 3),
        "silenceRatio": round(silence_ratio, 4),
        "clippedSampleCount": analysis.clipped_sample_count,
        "asrWordErrorRate": asr_word_error_rate,
        "stabilityPass": stability_pass,
    }


def select_candidate(results: list[dict[str, object]]) -> str | None:
    eligible = [
        result
        for result in results
        if result.get("licenseGate") == "pass"
        and result.get("r10StabilityGate") == "pass"
        and result.get("allRequiredScriptsRendered") is True
        and isinstance(result.get("emotionFidelity"), (int, float))
        and isinstance(result.get("naturalness"), (int, float))
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda item: (
            -cast(float, item["emotionFidelity"]),
            -cast(float, item["naturalness"]),
            str(item.get("candidateId") or ""),
        )
    )
    return str(eligible[0]["candidateId"])
