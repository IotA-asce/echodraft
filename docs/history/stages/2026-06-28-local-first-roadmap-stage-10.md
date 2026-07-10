# Stage 10 - Sound Design

Goal: add local sound assets, scene-level sound cues, conservative chapter mixing, and dashboard controls while keeping clean narration as the default output.

## Scope

- Extend existing ambience records into typed sound assets and cues for ambience, music, and SFX.
- Import local WAV assets into project artifacts without storing audio blobs in the database.
- Assign cues to scenes with gain, fades, ducking, and target mix mode.
- Assemble explicit clean, light, and dramatized chapter renders.
- Write sound stem and mixed WAV artifacts with manifest lineage.
- Add a Sound Design panel to the chapter production workflow.

## Validation

- Add regression coverage for WAV import, cue assignment, clean default production, manifest data, and non-silent light mix output.
- Run backend tests, Ruff, mypy, web typecheck, web lint, and targeted smoke testing where available before merge.

## Boundaries

- Clean narration remains the default production path.
- No cloud sound or music generation is added.
- The mixer is intentionally conservative and local-only.
- Non-WAV source import is deferred to a later FFmpeg conversion workflow.
