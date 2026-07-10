from __future__ import annotations

from dataclasses import dataclass

from echodraft_domain import DirectionProfile

ALL_DIRECTION_CONTROLS = {
    "pace",
    "intensity",
    "tone",
    "emotion",
    "pauseBeforeMs",
    "pauseAfterMs",
    "emphasis",
    "whisper",
    "stylePrompt",
    "noSfx",
}


@dataclass(frozen=True)
class CompiledDirection:
    engine_controls: dict[str, object]
    effective_direction: dict[str, object]
    unsupported_direction: list[str]


def compile_direction(
    profile: DirectionProfile,
    *,
    engine_id: str,
    setup_mode: str | None,
    direction_support: set[str],
) -> CompiledDirection:
    unsupported = sorted(ALL_DIRECTION_CONTROLS - direction_support)
    if engine_id == "kokoro" and setup_mode == "managed_onnx":
        return CompiledDirection(
            engine_controls={"speed": profile.pace},
            effective_direction={"pace": profile.pace},
            unsupported_direction=unsupported,
        )
    if engine_id == "piper":
        controls: dict[str, object] = {
            "lengthScale": max(0.5, min(2.0, 1 / profile.pace))
        }
        if profile.pause_after_ms:
            controls["sentenceSilence"] = profile.pause_after_ms / 1000
        return CompiledDirection(
            engine_controls=controls,
            effective_direction={
                "pace": profile.pace,
                "pauseAfterMs": profile.pause_after_ms,
            },
            unsupported_direction=unsupported,
        )
    return CompiledDirection(
        engine_controls={},
        effective_direction={},
        unsupported_direction=unsupported,
    )
