# Phase 2 — Publishable Audio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close gaps G11, G5, G13 per [`docs/product/roadmap.md`](../../product/roadmap.md) Phase 2: exports meet ACX-style loudness/true-peak targets, ship as a tagged chapter-marked M4B (and tagged MP3) with a retail sample, and carry a trustworthy QA scorecard.

**Architecture:** Three sequential tasks (stream B), each on its own feature branch off latest `main`, merged `--no-ff` and pushed after task review. Runs in parallel with the Phase 1 stream. **Ordering constraint:** B1 (G5) rewrites `assembly.py` — it must not run concurrently with Phase 1's A1 (G4, also touches `assembly.py`); B1 starts only after A1 is merged. B2 (G11) is file-disjoint from stream A and runs first.

**Tech Stack:** Python 3.12/FastAPI, stdlib `wave` + **numpy (new dep)** for in-process analysis/mix math, **ffmpeg (already a required system tool** — `model_catalog.yaml` lists it required with "future mixing, and loudness workflows"; `exporting.py` already shells out to it) for resampling/loudness/limiting/encoding/muxing.

## Global Constraints

Same as Phase 0 plan Global Constraints (branch/verify/merge/push, append-only history, no audio blobs in DB, migration + repair pairing, mypy strict, ruff, docs updated, CI green after merge — `gh run list --branch main`). Additionally:
- **ffmpeg-dependent behavior must degrade honestly:** every new ffmpeg invocation follows the existing pattern (`shutil.which("ffmpeg")` gate → explicit blocker/issue, `exporting.py:265-268`), never a silent skip.
- **Tests must not require ffmpeg or produce real loudness-normalized audio to pass CI**: unit-test the analysis math (numpy paths) on fabricated WAVs; for ffmpeg-dependent steps, test command construction via monkeypatched `subprocess.run` (pattern: `test_kokoro_setup.py`) plus gating behavior. Where CI runners have ffmpeg (ubuntu-latest does), an integration test may run it, but must skip cleanly (`pytest.mark.skipif(not shutil.which("ffmpeg"))`) — the only permitted skip, matching the export tests' existing treatment of ffmpeg.
- Loudness/mastering targets (write them into code as named constants): integrated loudness **-19 LUFS** (±1 tolerance in QA), true peak **≤ -3 dBTP**, loudness range target LRA 11 (informational), room tone: **1000 ms head / 2000 ms tail** of pink noise at **≈ -70 dBFS RMS** (ACX rejects pure digital silence), noise floor check ≤ -60 dB RMS.

---

### Task B2 (G11): Real audio QA metrics feeding readiness — *runs first; file-disjoint from Phase 1*

**Branch:** `feat/g11-real-audio-qa`

**Problem (confirmed):** Render metadata hardcodes `"peak": 0, "silenceRanges": [[0, duration]], "waveform": []` (`rendering.py:76-90`); assembly writes `"peaks": []` and an unconditional `"status": "passed"` validation file (`assembly.py:141-153`); `review_workbench.py:_waveform` (:168-187) serves these fakes to the UI as real analysis. `_audio_rules` (`review.py:178-203`) checks only naive per-sample clip threshold and literal all-zero-bytes silence; readiness `_audio_error` (`readiness.py:679-691`) only decodes+compares duration. No LUFS/RMS/dead-air/truncation checks exist despite `qa-rulebook.md` promising them.

**Files:**
- Create: `apps/api/src/echodraft_api/audio_analysis.py` — the shared analysis module (B1/B3 reuse it)
- Modify: `apps/api/pyproject.toml` — add `numpy>=2.0`
- Modify: `apps/api/src/echodraft_api/rendering.py` (write real peak/silenceRanges/waveform), `apps/api/src/echodraft_api/assembly.py` (real waveform peaks + validation derived from analysis — **only** the telemetry-writing lines :141-153, do NOT touch mixing/pauses; stream A owns those), `apps/api/src/echodraft_api/review.py` (`_audio_rules` real metrics), `apps/api/src/echodraft_api/readiness.py` (audio checks consume stored metrics)
- Modify docs: `docs/pipeline/qa/qa-rulebook.md` (mark implemented checks), `docs/pipeline/qa/readiness-qa.md`
- Test: create `apps/api/tests/test_audio_analysis.py`; extend `apps/api/tests/test_review.py`, `test_readiness.py`

**Interfaces:**
- Produces `audio_analysis.analyze_wav(path: Path) -> AudioAnalysis` (dataclass or TypedDict) computed with numpy from PCM16 frames:
  - `peak_dbfs: float` (20*log10(max|s|/32768), -inf→-120.0 floor)
  - `rms_dbfs: float` (whole-file RMS)
  - `dead_air_ranges: list[tuple[int, int]]` — maximal runs ≥ 3000 ms where 500 ms sliding-window RMS < -60 dBFS, excluding the first/last window (head/tail room tone is legitimate)
  - `waveform_peaks: list[float]` — 200 evenly-bucketed normalized max-abs values (0..1) for UI
  - `silence_ranges: list[tuple[int, int]]` — same windows as dead-air but with no minimum-length threshold ≥ 500 ms (feeds the existing metadata key honestly)
  - `duration_ms: int`, `sample_rate: int`, `clipped_sample_count: int` (|s| ≥ 32760)
- Truncation heuristic in `_audio_rules` (needs text): expected speech duration floor = `len(synthesis_text) / 30 * 1000` ms (30 chars/sec is fast speech); flag `truncation_suspected` (severity warning) when `duration < 0.5 * floor` and `len(text) > 40`. Read `synthesisText` from the render's `request_json` — already loaded in `qa_segment`.
- New/updated `_audio_rules` findings (keep existing categories where they exist): `clipping` now uses `clipped_sample_count > 8` (isolated inter-sample rounding ignored); `excessive_silence` becomes real: total dead-air > 20% of duration or any single range ≥ 5000 ms; `dead_air` (new, warning) for any range in `dead_air_ranges`; `low_loudness`/`high_loudness` (warning) when `rms_dbfs` outside [-30, -14] (rough segment-level bounds; exact LUFS gating arrives with mastering in B1); `truncation_suspected` as above.
- Rendering metadata keys keep their names (`peak`, `silenceRanges`, `waveform`) but now carry: `peak` = peak_dbfs, `silenceRanges` = real ranges, `waveform` = waveform_peaks. `review_workbench._waveform` needs no change (it passes through) — but verify its consumers tolerate float peak (check `SegmentInspectorPanel`/`ChapterAudioPlayer` usage; adjust frontend display if it assumed int 0).
- Readiness `_audio_checks`: chapter-audio check gains metrics from analyzing the chapter WAV (peak ≤ -3 dBFS else warning `chapter_audio_hot`; dead-air per above as warning) — same stable check ids across pass/fail per Task 3's convention (one id, `reason` in metadata).
- Consumes: nothing from stream A. Does NOT change sample rates, mixing, or export — that's B1/B3.

**Steps:**

- [ ] **Step 1 (RED): analysis unit tests** (`test_audio_analysis.py`). Extract/adapt `test_sound_design.py::wav_bytes` into a shared helper (move to `apps/api/tests/audio_fixtures.py`; update test_sound_design import) that can fabricate WAVs with: given amplitude square wave, inserted silent spans, given sample rate. Cases: known-amplitude wave → expected peak/rms (±0.5 dB); 4 s silence inserted mid-file → one dead-air range covering it; clipped samples counted; waveform_peaks length 200, max ≈ 1.0.
- [ ] **Step 2: implement `audio_analysis.py`** with numpy (add dep; `uv sync`). GREEN.
- [ ] **Step 3 (RED→GREEN): real telemetry.** Test: render a segment via mock provider (writes silence) → metadata JSON's `peak` ≈ -120 (silence), `silenceRanges` non-fake, `waveform` has 200 entries. Then implement in `rendering.py` (call analyze_wav after synthesis; write real values) and assembly's telemetry lines (real peaks; validation status derived: "passed" only when no blocking finding from analysis). Verify inspector waveform endpoint still serves correctly (existing `test_review.py` inspector test).
- [ ] **Step 4 (RED→GREEN): QA rules.** Tests per new rule using fabricated renders (insert crafted WAV + matching render row like Task 3's seeded-issue pattern, or render then overwrite the WAV file before invoking qa — choose the cleaner existing pattern). Truncation test: long text + short audio → flagged; normal ratio → not flagged.
- [ ] **Step 5 (RED→GREEN): readiness consumption** with stable check ids + `reason` metadata.
- [ ] **Step 6: full battery** (backend; frontend only if display tweaks were needed → web lint/typecheck), docs, commit `feat(qa): real audio analysis replaces faked telemetry`, merge, push, CI green.

---

### Task B1 (G5): 44.1 kHz mastered pipeline — *starts only after Phase 1's A1 (G4) is merged*

**Branch:** `feat/g5-mastered-audio`

**Problem (confirmed):** pipeline ceiling is `ChapterAssembler.sample_rate = 16_000` (assembly.py:52); `_resample` (:444-455) is linear interpolation with no anti-aliasing; mix hard-clips (`_clip_sample`, :474-476); fixed pauses (handled by A1); no room tone; ambience loops seam without crossfade and ducking is a static -6 dB; per-sample Python list math won't scale at 44.1 kHz; managed Kokoro writes float32 WAVs stdlib `wave` can't parse (latent — `kokoro_setup.py:422` soundfile default subtype).

**Files:**
- Modify: `apps/api/src/echodraft_api/assembly.py` — sample_rate 44100; numpy mix path; master via ffmpeg; room tone; equal-power crossfade on ambience loop boundaries + fade curves; keep A1's pause logic intact (rebase carefully)
- Create: `apps/api/src/echodraft_api/mastering.py` — ffmpeg invocations: `resample_wav(src, dst, rate)` (`-af aresample=resampler=soxr -ar 44100 -ac 1`), `measure_loudness(path) -> {input_i, input_tp, input_lra, input_thresh}` (loudnorm print_format=json first pass), `master_wav(src, dst, measured)` (two-pass `loudnorm=I=-19:TP=-3:LRA=11:measured_*=...` + `alimiter=limit=0.7079` [-3 dBTP] `:level=false`), `room_tone(duration_ms, rate) -> np.ndarray` (pink-ish noise at -70 dBFS RMS, generated with numpy — no ffmpeg needed)
- Modify: `apps/api/src/echodraft_api/kokoro_setup.py` — wrapper writes PCM16 (`soundfile.write(..., subtype="PCM_16")`); wrapper self-heal from A1 propagates it
- Modify: `apps/api/src/echodraft_api/tts_providers.py` — `MockTtsAdapter` stays 16 kHz (exercises resampling); no other provider change
- Modify: `apps/api/src/echodraft_api/rendering.py` — after synthesis, if WAV rate ≠ 44100, resample via `mastering.resample_wav` when ffmpeg present, else keep native rate and record `"resampled": false` (assembly still resamples in-process as fallback — upgrade `_resample` to a windowed-sinc numpy implementation so the fallback is band-limited too)
- Modify: `apps/api/src/echodraft_api/readiness.py`/`review.py` — loudness QA bounds tighten to mastered targets for chapter-level checks (LUFS from `measure_loudness` when ffmpeg present: integrated -19 ±1 → pass, else warning `chapter_loudness_out_of_range`)
- Modify docs: `docs/pipeline/assembly/sound-design.md`, `docs/architecture/current-pipeline-behavior.md`, `docs/pipeline/qa/qa-rulebook.md`
- Test: `apps/api/tests/test_assembly.py` (44100 assertions replace 16000 — including the pre-existing `getframerate() == 16_000` assertion at ~:72-74), `test_sound_design.py` (crossfade/duck/limiter behavior on fabricated waves), new `test_mastering.py` (command construction monkeypatched + skipif-ffmpeg integration case)

**Interfaces:**
- Produces: assembled chapter WAVs at 44100 Hz mono PCM16, loudness-normalized and true-peak-limited when ffmpeg is available; when ffmpeg is missing, assembly still produces 44.1 kHz output via the numpy band-limited fallback but records `"mastered": false` in the chapter manifest and readiness raises the existing-style blocker (`ffmpeg_missing` pattern) on export-readiness. Room tone head/tail applied at mastering stage. Chapter manifest gains `"mastering": {"targetLufs": -19, "truePeakDb": -3, "measured": {...}, "mastered": bool, "roomToneMs": {"head": 1000, "tail": 2000}}`.
- Mix path: `_samples_from_wav`/`_write_samples`/`_mix` move to numpy arrays (int32 accumulate → limiter headroom → PCM16); `_cue_gain` ducking stays -6 dB static this phase **but** applied with 50 ms gain ramps (no zipper); ambience loop tiling gets 250 ms equal-power crossfade at each seam; cue fade in/out become equal-power curves.
- Consumes: A1's per-segment pause logic in `_write_speech_stem` (merged before this task); B2's `audio_analysis` + fixtures.

**Steps:**

- [ ] **Step 1 (RED):** update `test_assembly.py` framerate assertions to 44100 and add: mock 16 kHz renders → assembled chapter reports 44100 and duration within 2% of expected (resampling correctness); fabricated sine via fixtures at 16 kHz resampled by the numpy fallback contains no energy above 8 kHz alias mirror (assert via numpy FFT on the output — keep tolerance loose; this is the band-limiting proof).
- [ ] **Step 2: numpy fallback resampler + 44100 target + numpy mix path.** GREEN for step 1.
- [ ] **Step 3: mastering module** — construction-only tests (monkeypatch subprocess.run, assert exact filter strings incl. two-pass measured values threading) + `skipif` integration test (real ffmpeg: master a fabricated -30 dBFS wave, re-measure, assert -19 ±1.5 LUFS and TP ≤ -3).
- [ ] **Step 4: room tone + wire mastering into assembly** (after stem write, before QA/telemetry), manifest block, honest degradation when ffmpeg missing. Test: assembled output starts/ends with ~-70 dBFS (not digital silence, not speech) using analysis fixtures.
- [ ] **Step 5: ambience crossfade + ramped ducking** — extend `test_sound_design.py`: looped short asset → no discontinuity > 0.3 amplitude step at seam; duck transition contains intermediate gain values.
- [ ] **Step 6: Kokoro PCM16 wrapper fix + rendering-time resample.**
- [ ] **Step 7: full battery, docs, commit `feat(audio): 44.1 kHz band-limited pipeline with R128 mastering and room tone`, merge, push, CI green.**

---

### Task B3 (G13): M4B + tagged MP3 + retail sample + export QA scorecard

**Branch:** `feat/g13-export-polish`

**Problem (confirmed):** M4B has no code path (permanent `m4b_planned` blocker, `exporting.py:239-248`, raise at :73-76; UI button permanently disabled, `ExportPanel.tsx:116-118`); MP3 gets no ID3/cover (`_write_mp3`, :410-433); cover is only copied as a loose zip file (`_copy_cover`, :435-444); no retail sample; manifest (schema 0.2.0) has no QA block; no cover persistence (only per-request `cover_image_path`).

**Files:**
- Modify: `apps/api/src/echodraft_api/exporting.py` — M4B writer (concat + FFMETADATA chapters + AAC + cover attached_pic), MP3 `-metadata` ID3 + APIC cover, retail sample generator, per-output QA measurement into manifest `qa` block (bump `EXPORT_MANIFEST_VERSION` to "0.3.0"), remove the unconditional m4b blocker (keep `ffmpeg_missing` gating)
- Modify: `libs/domain-models/src/echodraft_domain/models.py` — `ExportRequest` gains `include_retail_sample: bool = False`, `ExportPackage`/manifest models expose the scorecard (check exact model shapes first)
- Modify: `apps/web/app/components/export/ExportPanel.tsx` — enable M4B button, retail-sample checkbox, render the QA scorecard of the latest export; `apps/web/app/api.ts` types
- Modify docs: `docs/pipeline/export/export-polish.md` (now-implemented matrix), `docs/architecture/pipeline-manifest-spec.md`
- Test: extend `apps/api/tests/test_production_workbench.py` — **flip `test_export_estimate_marks_mixed_gate_and_m4b_as_planned` (:153-184) to the success contract**; new M4B/MP3/sample/scorecard tests (command-construction via monkeypatch + skipif-ffmpeg integration)

**Interfaces:**
- M4B: chapters concat in `order_index` order via ffmpeg concat demuxer (list file of chapter WAVs from the export staging set — the mastered renders B1 produces); FFMETADATA `[CHAPTER] TIMEBASE=1/1000 START/END title=` blocks computed from each chapter's `duration_ms`; `-c:a aac -b:a 128k`; `-metadata title/artist/album/genre=Audiobook/date`; cover via second input + `-map 1 -c:v mjpeg -disposition:v attached_pic`; output `audiobook.m4b` in the package (inside the zip AND as a directly-downloadable output entry in the manifest).
- MP3: existing per-chapter files gain `-metadata title={chapterTitle}/artist={author}/album={title}/track={n}/{total}` and cover APIC (`-i cover -map 0:a -map 1:v -c:v mjpeg -id3v2_version 3 -disposition:v attached_pic`).
- Retail sample: when requested and format is mp3/m4b — first up-to-300 s of the first chapter (ffmpeg `-t 300` from that chapter's mastered WAV) → `retail_sample.mp3` (192k, same ID3 minus track), listed in manifest with its own QA entry.
- Scorecard: per output file — `{lufsIntegrated, truePeakDb, durationMs, bytes, sha256}` (measurement via `mastering.measure_loudness` when ffmpeg present, else `audio_analysis` peak/rms with `"method": "rms_fallback"`), plus package-level `{targetLufs: -19, truePeakCeilingDb: -3, allWithinTolerance: bool}` under manifest key `"qa"`. ExportPanel shows ✓/✗ per output.
- Consumes: B1's `mastering.measure_loudness` + mastered chapter renders; B2's `audio_analysis`; existing `ChapterRecord.title`/`order_index`/`duration_ms` and `ExportRequest.cover_image_path` (project-level cover persistence stays out of scope — YAGNI, the request field works).

**Steps:**

- [ ] **Step 1 (RED):** flip the m4b-planned test to expect a successful estimate (no `m4b_planned` blocker when ffmpeg present — monkeypatch `shutil.which`) and a real `.m4b` output entry in a mocked-subprocess export; add FFMETADATA unit test (given 3 chapters with known durations → exact CHAPTER blocks) and MP3/ID3 + sample + scorecard command/manifest tests.
- [ ] **Step 2: implement export changes.** GREEN.
- [ ] **Step 3: skipif-ffmpeg integration test** — full mp3+m4b export of a tiny produced project on runners with ffmpeg; assert the m4b opens (`ffprobe` chapters count) and manifest `qa` filled.
- [ ] **Step 4: frontend** (button, checkbox, scorecard) + web lint/typecheck (+ smoke if it covers export panel).
- [ ] **Step 5: full battery, docs, commit `feat(export): chaptered M4B, tagged MP3, retail sample, QA scorecard`, merge, push, CI green.**

---

## Phase exit criteria (roadmap)
Exports pass an automated ACX-style loudness/true-peak check (B1+B3 scorecard); M4B opens with correct chapters/metadata in a standard player (B3 integration test via ffprobe); readiness carries real audio QA (B2).
