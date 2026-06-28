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

## Assembly

`POST /api/v1/projects/{projectId}/chapters/{chapterId}/assemble` accepts:

- `clean`
- `light`
- `dramatized`

Clean writes the speech stem only. Light and dramatized writes:

- `speech.wav`
- `sound-design.wav`
- `mix.wav`
- a chapter manifest with cue inputs, output paths, mode, and mixer warnings

## Dashboard

The Sound Design panel in chapter production supports:

- local WAV asset upload
- asset type selection
- current-scene cue assignment
- gain and mode controls
- explicit clean/light/dramatized assembly
