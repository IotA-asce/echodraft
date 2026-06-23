# Stage 05 — Segment generation

## Outcome

Generate, replay, and selectively regenerate immutable audio renders for individual segments.

## Implement

- Define `SegmentRenderRequest` with segment revision, speaker/voice assignment, effective direction, adapter/model version, output format, and input checksum.
- Generate a content-addressed render key from the complete request. Reuse a successful matching render rather than generating duplicate audio.
- Add `SegmentRender` records with status, artifact paths, duration, sample rate, waveform metadata, error details, and parent render ID when regenerated.
- Implement asynchronous render jobs, cancellation, timeout handling, retries limited to safe transient failures, and persistent job events.
- Store audio under `audio/segments/<segment-id>/<render-key>/`; retain previous successful outputs as immutable history.
- Extract duration, loudness, peak, silence ranges, and waveform data after generation; write sidecar metadata JSON.
- Expose render, replay, history, and regenerate APIs. Regeneration must create a new render, never overwrite the existing one.
- Build per-segment controls for generate, play, inspect effective settings, compare history, and choose the active render.

## Validation

- Test render-key stability, cache hits, artifact paths, state transitions, cancellation, and immutable history.
- Use the mock adapter to test rendering success, adapter errors, timeout, corrupt audio, and stale voice/direction dependencies.
- Confirm a user can render one segment, play it, change its direction, regenerate it, and restore a previous render.

## Done when

One segment can be rendered and replayed through the UI, with reproducible metadata and non-destructive regeneration history.
