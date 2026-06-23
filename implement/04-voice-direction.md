# Stage 04 — Voice preview and direction

## Outcome

Let users hear and save voice choices and direction before rendering an entire chapter.

## Implement

- Define a provider-neutral `TtsAdapter` interface for capability discovery, voice listing, preview synthesis, segment rendering, and normalized error reporting.
- Implement a deterministic mock adapter for tests and one local adapter suitable for Apple Silicon. Keep provider credentials and model configuration outside project artifacts.
- Define `DirectionProfile` fields: pace, intensity, tone, style prompt, emphasis, whisper/voice effect flags, and explicit no-SFX preference.
- Support project defaults, scene defaults, and segment overrides with clear precedence: segment → scene → project → adapter default.
- Add `POST /voices/preview` and persist preview request metadata, generated asset path, adapter/model version, and direction payload.
- Build UI controls for voice selection, sample text, preview playback, direction presets, sliders, and override indicators.
- Write a versioned `manifests/direction_manifest.json` that captures effective direction for every renderable segment.

## Validation

- Contract-test each adapter against the same mock fixtures.
- Test precedence resolution, invalid direction values, unavailable voices, timeouts, and preview cancellation.
- Manually verify that a user can preview a narrator and character with distinct direction profiles before starting generation.

## Done when

Users can preview a voice with a style prompt, save project/scene/segment direction, and produce a reproducible direction manifest.
