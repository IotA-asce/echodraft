# Stage 08 — Ambience and light cinematic layer

## Outcome

Offer optional, restrained ambience without compromising intelligibility or altering the speech-only workflow.

## Implement

- Define `AmbienceProfile`, `AmbienceCue`, and `AmbienceAsset` entities with licensing/provenance metadata, gain, fades, time range, and scene association.
- Implement render modes: `speech_only`, `multi_voice`, and `light_cinematic`. `speech_only` must bypass every ambience operation.
- Add a curated local asset library and an asset-reference workflow. Do not build autonomous music composition or unlicensed asset acquisition in the MVP.
- Let users assign ambience profiles at project or scene scope, lock scenes to no SFX, and override individual cues.
- Build a stem mixer that produces separate speech and ambience stems, applies gain/fade envelopes, prevents clipping, and records all mix parameters.
- Extend chapter render manifests to pin ambience inputs and mix configuration; existing speech-only chapter renders must remain valid.
- Add UI controls for ambience profile selection, cue inspection, mute/solo, gain adjustments, and A/B playback against speech-only output.

## Validation

- Test mode selection, no-SFX locks, cue ordering, fade envelopes, clipping prevention, and stem separation.
- Verify speech-only output remains byte-for-byte unaffected by ambience settings.
- Conduct manual listening tests for intelligibility at normal and headphone playback levels.

## Done when

Users can export a chapter with or without light ambience, adjust it independently from speech, and trace every included asset and mix decision.
