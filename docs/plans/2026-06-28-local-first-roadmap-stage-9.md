# Stage 9 - TTS Production Upgrade

Goal: formalize local TTS providers, add Piper fallback and XTTS-v2 opt-in paths, strengthen pronunciation-aware render fingerprints, and expose render queue/compare tooling.

## Scope

- Add a provider contract and registry for mock, Kokoro, Piper, and XTTS-v2.
- Keep Kokoro as the managed local real-audio path.
- Add Piper CLI settings for executable, model, optional config, and optional voice registry.
- Add XTTS-v2 settings for local Python runtime, reference WAV, language, and explicit consent.
- Persist render queue items for chapter production.
- Include provider identity and pronunciation replacements in render fingerprints.
- Add render comparison for the latest segment render and its parent.
- Add dashboard provider status, local provider setup, render queue, and compare controls.

## Validation

- Add regression tests for provider registry status, pronunciation-aware render staleness, render queue rows, and render compare fields.
- Run backend tests, Ruff, mypy, web typecheck, and web lint before merge.

## Boundaries

- No cloud fallback is added.
- Audio and reference voice files remain filesystem artifacts/paths, not database blobs.
- XTTS-v2 is opt-in and fails closed without explicit reference-voice consent.
