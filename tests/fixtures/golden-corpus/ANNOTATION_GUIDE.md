# Golden Corpus Annotation Guide

This guide defines the committed labels used by the v2 evaluation corpus. Raw public-domain book
text is fetched into `test-assets/golden-corpus/` and must not be committed. The labels in this
directory are original annotation work and are committed.

## File Layout

Each book directory may contain:

- `meta.json`: source and checksum metadata.
- `labels/chapters.json`: exhaustive chapter/story boundaries.
- `labels/scenes.json`: exhaustive scene boundaries.
- `labels/roster.json`: exhaustive character roster and aliases.
- `labels/attribution-sample.json`: stratified dialogue attribution sample.
- `labels/direction-sample.json`: selected direction annotations.
- `fixture-manifests/`: hand-corrected stage input manifests for isolated eval runs.

## Speaker Labels

Use these values for `goldSpeaker` in attribution labels:

- A canonical roster name when the speaker is identifiable.
- `"narrator"` when the line belongs to the narration voice rather than an in-world speaker.
- `null` with `"ambiguous": true` when a careful reader cannot confidently identify one speaker.

Do not force a name when two annotators disagree and the text does not resolve it. Ambiguity is a
valid expected output because the product must know when not to auto-approve a speaker.

## Required Attribution Fields

Every attribution sample row must include:

- `segmentAnchor`: stable location data, usually `chapterIndex`, `sceneIndex`, and
  `charOffsetInScene`.
- `quotedText`: the dialogue text being labeled.
- `goldSpeaker`: canonical roster name, `"narrator"`, or `null`.
- `ambiguous`: boolean.
- `annotators`: annotator ids.
- `agreement`: `unanimous`, `resolved`, or `disagreement`.

## Scene And Roster Rules

- A scene boundary is a material beat change: location, time, point of view, or present cast
  changes. Record `breakReason` as `location_change`, `time_skip`, `pov_shift`, or `cast_change`.
- Add an alias only when the text supports it. Preserve the exact surface form in `aliases`.
- Keep one roster entry per distinct character. Do not split honorifics, nicknames, and surnames
  into separate people when the text establishes they are the same character.

## Direction Labels

Direction rows should be labeled independently by at least two annotators. `goldEmotion` may
contain multiple acceptable labels when annotators choose different defensible terms. Record the
agreement note so model scores can be compared against the human ceiling.

## Labeling Discipline

Annotators must not inspect model output while labeling. Labels are ground truth for evaluation,
not tuned examples for a specific pipeline version.
