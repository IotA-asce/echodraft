# Stage 06 — Chapter assembly

## Outcome

Assemble active segment renders into a playable chapter speech stem.

## Implement

- Define `ChapterRender` and `ChapterRenderInput` records that pin the ordered active render ID for every included segment.
- Implement eligibility checks: all non-empty segments require successful active renders; warn on unresolved speakers, stale renders, and missing segments.
- Retrieve segment audio in scene/segment order, normalize the target sample rate and channel layout, and insert configurable pauses at paragraph, scene, and chapter boundaries.
- Assemble the speech stem with a deterministic audio pipeline; retain an input manifest and never mutate source segment audio.
- Write chapter assets under `audio/chapters/<chapter-id>/<chapter-render-id>/`, including `speech.wav`, `chapter_render_manifest.json`, waveform data, duration, and validation report.
- Add APIs to start assembly, inspect progress, fetch the active chapter render, and list historical chapter renders.
- Build a chapter playback UI with segment timeline markers, missing/stale indicators, duration, playback seeking, and jump-to-segment controls.

## Validation

- Test ordering, pause insertion, sample-rate conversion, missing-input rejection, and deterministic manifest generation.
- Use short synthetic WAV fixtures to verify duration and sample boundaries.
- Confirm a chapter can be assembled end-to-end from multiple segments and that changing one segment invalidates the relevant chapter render.

## Done when

A complete chapter speech stem can be generated, played, and traced back to the exact immutable segment renders used to create it.
