import wave
from pathlib import Path

from echodraft_api.orchestrator import HardwareSnapshot
from echodraft_api.tts_bakeoff import fixed_corpus, measure_render, preflight, select_candidate


def _tone(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes((b"\x00\x10" * 16000))


def test_bakeoff_corpus_has_all_required_scripts_and_long_stability_case() -> None:
    corpus = fixed_corpus()
    assert [script.id for script in corpus] == [
        "neutral",
        "angry",
        "whisper",
        "laughter",
        "grief",
        "long_stability",
        "multi_character",
        "pronunciation",
    ]
    long_case = next(script for script in corpus if script.id == "long_stability")
    assert len(long_case.text.split()) >= 1500


def test_preflight_records_license_and_runtime_gates() -> None:
    report = preflight(
        HardwareSnapshot(
            cpu_count=10,
            total_ram_gib=16,
            platform="darwin",
            machine="arm64",
        )
    )
    candidates = {item["id"]: item for item in report["candidates"]}
    assert candidates["chatterbox"]["license_gate"] == "pass"
    assert candidates["zonos"]["license_gate"] == "pass"
    assert candidates["orpheus"]["license_gate"] == "conditional"
    assert report["hardware"]["ttsDevice"] == "mps"


def test_render_measurement_and_selector_fail_closed(tmp_path: Path) -> None:
    wav = tmp_path / "render.wav"
    _tone(wav)
    measured = measure_render(wav, wall_clock_seconds=0.5, asr_word_error_rate=0.05)
    assert measured["rtf"] == 0.5
    assert measured["stabilityPass"] is True
    assert select_candidate([]) is None
    assert select_candidate(
        [
            {
                "candidateId": "zonos",
                "licenseGate": "pass",
                "r10StabilityGate": "pass",
                "allRequiredScriptsRendered": True,
                "emotionFidelity": 4.4,
                "naturalness": 4.2,
            },
            {
                "candidateId": "chatterbox",
                "licenseGate": "pass",
                "r10StabilityGate": "pass",
                "allRequiredScriptsRendered": True,
                "emotionFidelity": 4.6,
                "naturalness": 4.0,
            },
        ]
    ) == "chatterbox"
