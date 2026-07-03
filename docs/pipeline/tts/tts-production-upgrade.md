# TTS Production Upgrade

Stage 9 formalizes local TTS providers behind a single provider contract.

## Providers

- `mock`: built-in silent WAV provider for workflow validation.
- `kokoro`: managed ONNX setup or custom adapter. Kokoro remains the default real local voice path.
- `piper`: local CLI fallback. It requires a Piper executable and local `.onnx` model; optional config and voice registry paths can be supplied.
- `xtts_v2`: local Coqui XTTS-v2 adapter. It is opt-in and fails closed unless a local reference WAV path and explicit reference-voice consent are configured.

No provider silently falls back to cloud execution or another provider.

## Render Freshness

Segment render fingerprints now include:

- canonical segment text and revision;
- synthesis text after pronunciation replacement;
- resolved voice profile and provider voice ID;
- resolved direction;
- active TTS provider identity and model version;
- applied pronunciation entries.

Changing a pronunciation entry, active provider, model path, direction, voice assignment, or segment text stales only affected segment renders.

## Queue And Compare

Chapter production creates `render_queue_items` rows for each segment. Rows move through `queued`, `running`, `succeeded`, or `failed` and store metadata references only.

The render compare endpoint reports the latest segment render, its parent render, and changed request fields. This supports local review without rewriting render history.

## Reference Voices

XTTS-v2 reference voices are treated as local user-provided assets. Users must set `referenceVoiceConsent` before Echodraft will attempt synthesis. The relational database stores configuration metadata only; reference audio remains a filesystem path.
