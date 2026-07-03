# Sound Design

Stage 10 adds local sound design as an explicit opt-in layer on top of clean narration.

## Defaults

- Clean narration remains the default chapter output.
- Sound assets are local WAV files stored under project artifacts.
- The relational database stores only asset metadata, cue metadata, and artifact paths.
- Light and dramatized mixes must be assembled explicitly.

## Assets

Sound assets can be imported as:

- `ambience`
- `music`
- `sfx`

The current local Python mixer accepts WAV input. Other formats should be converted with a local tool such as FFmpeg before import.

## Cues

Sound cues attach an asset to a scene with:

- cue type
- start offset in milliseconds
- gain
- fade in/out
- ducking
- target mix mode: `light`, `dramatized`, or `all`

Light mode applies conservative gain ceilings. Dramatized mode allows slightly stronger layers but still ducks cue audio under narration.

Cue placement is band-limited and click-free (Phase 2 task B1):

- Ambience/music loops are tiled to length with a **250 ms equal-power crossfade** at each
  loop seam, so a short asset repeats without an audible click or level bump.
- Cue fade in/out use equal-power (`sqrt`) curves.
- Ducking stays a static **-6 dB** dip under narration, but the level change is applied with
  **50 ms gain ramps** at the boundaries rather than an instant step (no zipper noise).

## Mixing and mastering

The mixer runs entirely in numpy (no per-sample Python loops):

- The pipeline sample rate is **44.1 kHz mono PCM16**. Segment renders at other rates are
  resampled to 44.1 kHz — via ffmpeg's soxr resampler at render time when ffmpeg is present,
  otherwise by an in-process **band-limited (Fourier-method) fallback** during assembly, so
  no alias images leak into the 44.1 kHz band either way.
- The float mix bus is soft-limited into PCM16; ffmpeg's `alimiter` does the real true-peak
  limiting at the mastering stage.

Every assembled chapter is **mastered** as the final step:

- **Room tone** — 1000 ms head / 2000 ms tail of faint pink-ish noise at ≈ -70 dBFS RMS is
  laid at the boundaries (ACX rejects pure digital silence). It is generated with numpy, so
  it needs no ffmpeg, and it is boundary-excluded by dead-air analysis.
- When **ffmpeg is present**, the room-toned bed is loudness-normalised to **-19 LUFS**
  (two-pass linear `loudnorm`) and true-peak-limited to **-3 dBTP** (`alimiter`), and the
  chapter manifest's `mastering` block records `"mastered": true` plus the measured stats.
- When **ffmpeg is missing**, the un-mastered 44.1 kHz room-toned bed is still written but the
  manifest records `"mastered": false`, and export readiness raises the honest `ffmpeg_missing`
  blocker rather than shipping a falsely-labelled master.

## Assembly

`POST /api/v1/projects/{projectId}/chapters/{chapterId}/assemble` accepts:

- `clean`
- `light`
- `dramatized`

Clean writes the speech stem only (then masters it). Light and dramatized writes:

- `speech.wav`
- `sound-design.wav`
- `mix.wav` (the mastered deliverable)
- a chapter manifest with cue inputs, output paths, mode, mixer warnings, and a `mastering`
  block (`targetLufs`, `truePeakDb`, `lra`, `mastered`, `roomToneMs`, `measured`)

## Dashboard

The Sound Design panel in chapter production supports:

- local WAV asset upload
- asset type selection
- current-scene cue assignment
- gain and mode controls
- explicit clean/light/dramatized assembly
