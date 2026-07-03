# QA Rulebook

See also: [voice-bible-spec.md](../casting/voice-bible-spec.md), [pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md), [mvp-product-spec.md](../../product/mvp-product-spec.md)

## Purpose
Define the automated and human review standards for the MVP. The quality target is not human-studio perfection; it is a trustworthy, immersive, patchable premium draft.

## QA layers
1. Automated technical QA
2. Automated linguistic QA
3. Automated narrative QA
4. Human editorial QA
5. Human listening QA

## Automated technical checks
Required checks:
- missing segment render detection
- file existence validation
- zero-duration render detection
- clipping detection
- abnormal silence detection
- chapter loudness bounds
- corrupted export detection

Rules:
- missing segment render is `blocking`
- unreadable audio file is `blocking`
- suspected truncation is `blocking`
- clipping above threshold is at least `warning`
- severe ambience masking may escalate to `error`

## Automated linguistic checks
Required checks:
- pronunciation dictionary coverage hits and misses
- repeated word anomaly detection
- obvious text truncation detection
- probable attribution mismatch detection
- unsupported symbol detection

Rules:
- repeated word anomalies are `warning`
- attribution mismatch is `warning` or `error` depending on confidence
- pronunciation misses affecting key names should open actionable issues

## Automated narrative checks
Recommended checks:
- narrator versus character voice confusion
- sudden style drift within a scene
- ambience masking speech threshold violations
- chapter render completeness

## Human editorial checklist
For each reviewed chapter, ask:
1. Are all lines present?
2. Are major character voices distinguishable?
3. Does narration feel stable and consistent?
4. Are pronunciations acceptable?
5. Are emotional cues appropriate without overacting?
6. Is any line unintentionally robotic, funny, or melodramatic?
7. Is ambience distracting or too loud?
8. Are pauses natural?
9. Does the chapter feel coherent end-to-end?
10. Which lines need regeneration?

## Human listening rubric
Rate each 1 to 5:
- Intelligibility
- Voice consistency
- Character separation
- Emotional appropriateness
- Narrative flow
- Production restraint
- Overall immersion

## Severity levels
- `info`: note only
- `warning`: should be reviewed; export may still proceed
- `error`: materially hurts quality and should normally be fixed
- `blocking`: prevents chapter approval or export

## Issue categories
- `pronunciation`
- `attribution`
- `clipping`
- `loudness`
- `missing_audio`
- `voice_drift`
- `timing`
- `ambience_masking`
- `editorial`
- `truncation`

## Approval rules
### Segment approval
A segment may be approved only if:
- audio exists
- no blocking issue exists
- the active render is acceptable in context

### Chapter approval
A chapter may be approved only if:
- all segments have active renders
- no blocking issue remains
- chapter-level QA has passed
- remaining warnings are consciously accepted

### Export approval
A project may be exported only if:
- rights declaration exists
- each included chapter has an approved chapter render
- no project-level blocking issue remains

## Regression triggers
Rerun targeted QA when any of the following change:
- pronunciation dictionary
- voice profile
- narrator assignment
- segment regeneration
- chapter reassembly
- export packaging configuration

## MVP acceptance thresholds
The MVP is quality-acceptable when:
- users can identify major characters reliably
- narration stays stable across a chapter
- obvious technical defects are rare and patchable
- ambience remains subtle
- listeners rate immersion above generic TTS
