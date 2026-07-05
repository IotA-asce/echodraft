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

**Implemented** (Phase 2 task B2/G11, `echodraft_api.audio_analysis`): every check below is
computed from real PCM analysis (numpy, no ffmpeg) instead of hardcoded placeholders. See
`AudioAnalysis` for the exact metrics (`peak_dbfs`, `rms_dbfs`, `dead_air_ranges`,
`silence_ranges`, `waveform_peaks`, `clipped_sample_count`) and `ReviewService._audio_rules`
for the thresholds:
- `clipping`: `clipped_sample_count > 8` (isolated inter-sample rounding is ignored)
- `excessive_silence`: total dead-air time > 20% of duration, or any single dead-air run
  ≥ 5000 ms
- `dead_air` (new): any run ≥ 3000 ms where 500 ms-windowed RMS stays below -60 dBFS,
  excluding runs that touch the very start or end of the file (head/tail room tone is
  legitimate and is not "dead")
- `low_loudness` / `high_loudness`: whole-file RMS outside `[-30, -14]` dBFS -- rough
  segment-level bounds that stay the proxy for un-mastered *segment* renders
- `truncation_suspected` (new): expected speech floor is `len(text) / 30 chars-per-sec`;
  flagged when actual duration is under half that floor and the text exceeds 40 characters

**Chapter loudness bounds** (Phase 2 task B1/G5): once a chapter is mastered (ffmpeg present)
its measured integrated loudness gates directly against the target:
- `chapter_loudness_out_of_range` (review, `warning`): the mastered chapter's integrated
  loudness is outside **-19 LUFS ±1**.
- `chapter_loudness_{chapterId}` (readiness, stable-id pass/fail): passes only when the chapter
  was actually mastered and lands within -19 LUFS ±1; otherwise a `warning` flags loudness as
  unverified at target (`reason` = `out_of_range` when mastered, `unmastered` when ffmpeg was
  missing).
- `export_mastering` (readiness, `blocking`): honest degradation — when ffmpeg is missing,
  chapters cannot be mastered to -19 LUFS / -3 dBTP, so export readiness is blocked
  (`reason` = `ffmpeg_missing`), mirroring the export pipeline's ffmpeg gate.

Rules:
- missing segment render is `blocking`
- unreadable audio file is `blocking`
- suspected truncation is `warning` (escalates to `blocking` once chapter-level truncation
  gating lands with export QA in task B3)
- clipping above threshold is at least `warning`
- severe ambience masking may escalate to `error`

## Automated linguistic checks
Required checks:
- pronunciation dictionary coverage hits and misses
- repeated word anomaly detection
- obvious text truncation detection
- probable attribution mismatch detection
- unsupported symbol detection

**Implemented** (Phase 3 G16): local ASR word-match verification can run after each segment
render when `ECHODRAFT_ASR_EXECUTABLE` or `whisper-cli` on `PATH` and
`ECHODRAFT_ASR_MODEL_PATH` are configured. The first adapter targets whisper.cpp's CLI
contract (`-m <model> -f <wav> -oj -of <output_prefix>`). It writes
`asrVerification` into the segment render metadata, including transcript preview,
expected preview, match ratio, word error rate, missing/extra word samples, provider, model,
and segment render ID.

Rules:
- `asr_word_mismatch` is a `warning` when the normalized word match ratio is below `0.90`
- `asr_verification_error` is a `warning` when configured local ASR fails closed
- very short expected text below 4 normalized tokens is skipped as `skipped_short_text`
- readiness check `segment_asr_word_match` summarizes latest segment render ASR evidence

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
- `low_loudness`
- `high_loudness`
- `dead_air`
- `excessive_silence`
- `truncation_suspected`
- `asr_word_mismatch`
- `asr_verification_error`
- `missing_audio`
- `corrupt_audio`
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
