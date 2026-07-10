from echodraft_api.direction_compiler import ALL_DIRECTION_CONTROLS, compile_direction
from echodraft_domain import DirectionProfile


def _directed_profile() -> DirectionProfile:
    return DirectionProfile(
        scopeType="segment",
        scopeId="seg_direction_compiler",
        pace=1.25,
        intensity=0.9,
        tone="restrained",
        emotion="angry",
        pauseBeforeMs=125,
        pauseAfterMs=375,
        emphasis=True,
        whisper=True,
        stylePrompt="controlled urgency",
        noSfx=False,
    )


def test_managed_kokoro_compiles_only_native_pace() -> None:
    compiled = compile_direction(
        _directed_profile(),
        engine_id="kokoro",
        setup_mode="managed_onnx",
        direction_support={"pace", "pauseBeforeMs", "pauseAfterMs"},
    )

    assert compiled.engine_controls == {"speed": 1.25}
    assert compiled.effective_direction == {"pace": 1.25}
    assert compiled.unsupported_direction == sorted(
        ALL_DIRECTION_CONTROLS - {"pace", "pauseBeforeMs", "pauseAfterMs"}
    )


def test_piper_compiles_pace_and_sentence_silence() -> None:
    compiled = compile_direction(
        _directed_profile(),
        engine_id="piper",
        setup_mode="local_cli",
        direction_support={"pace", "pauseBeforeMs", "pauseAfterMs"},
    )

    assert compiled.engine_controls == {
        "lengthScale": 0.8,
        "sentenceSilence": 0.375,
    }
    assert compiled.effective_direction == {
        "pace": 1.25,
        "pauseAfterMs": 375,
    }


def test_custom_kokoro_and_xtts_remain_neutral_and_truthful() -> None:
    for engine_id, setup_mode in (
        ("kokoro", "custom_adapter"),
        ("xtts_v2", "coqui_local"),
    ):
        compiled = compile_direction(
            _directed_profile(),
            engine_id=engine_id,
            setup_mode=setup_mode,
            direction_support={"pauseBeforeMs", "pauseAfterMs"},
        )
        assert compiled.engine_controls == {}
        assert compiled.effective_direction == {}
        assert "emotion" in compiled.unsupported_direction
        assert "whisper" in compiled.unsupported_direction
