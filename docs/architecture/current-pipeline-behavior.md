# Current Pipeline Behavior

Document date: 2026-06-28

This document records the alpha pipeline behavior before the local-first roadmap stages deepen ingestion, cleaning, structure editing, local AI, casting, direction, QA, and export. It is intentionally descriptive, not aspirational.

## Ingestion

The current ingestion service accepts TXT, Markdown, DOCX, EPUB, and PDF files through `/api/v1/projects/{project_id}/source/import`.

- Source originals are copied into the project artifact store before parsing.
- Canonical text is written to `source/canonical/{source_id}.md` and copied to `source/canonical.md`.
- A source manifest is written under `manifests/source_manifest.{source_id}.json`.
- Cleaning now runs before canonical normalization. It removes explicit page markers such as `<!-- Page 9 -->`, `Page 9`, and `[9]`, repairs simple line-break hyphenation, merges broken wraps, and removes repeated running headers/footers when page breaks are available.
- Suspicious OCR-like tokens remain in canonical text but create open Clean Text Review issues.
- Normalization then performs Unicode normalization, newline cleanup, smart-quote and dash conversion, adjacent duplicate paragraph removal, and unusually long paragraph warnings.
- Cleaning decisions are written to a cleaning manifest under `sources/{source_id}/cleaning/` and to `text_cleanliness_issues` for review.

## PDF Handling

PDF ingestion uses `pypdf` to extract embedded text per page and invokes local OCR for pages whose extracted text is below the minimum text threshold.

- Mixed PDFs are handled page by page: readable embedded text is kept and low-text pages are rendered/OCRed.
- OCR requires Poppler `pdftoppm` and Tesseract to be available on `PATH`.
- OCR is limited to 150 candidate pages in the alpha implementation.
- Page images are rendered when Poppler is available.
- Per-page embedded text, selected text, OCR JSON/text artifacts, extraction method, confidence, and warnings are persisted separately from canonical text.
- Canonical spans preserve approximate page-to-canonical offset mappings.

## Structure

The structure service reads the latest canonical source and replaces the project chapter/scene/segment hierarchy. Extraction is now a staged local compiler pipeline: block map, chapter candidates, scene candidates, quote-aware atoms, renderable segments, optional local atom grouping, cast discovery, speaker attribution, and quality reporting.

- Chapters are detected from Markdown headings, `Chapter N`, prologue/epilogue, part, and book headings.
- Text before the first chapter heading is represented as front matter.
- If no chapter boundary is found, a single unresolved chapter is created with a parser warning.
- Scenes are detected from separator lines such as `***`, `---`, `####`, or `Scene N`; conservative time-shift and section-heading guesses become reviewable possible scene breaks.
- Segments are built from source-ordered atoms under `maxSegmentChars`, with DB-compatible narration, dialogue, and performance-beat segment types.
- Richer production types and speaker rules are stored in `parserEvidence`.
- Basic speaker candidates are inferred from `Name:`, quote/tag, tag/quote, inverted tag, and action-beat patterns.
- When the default Ollama model is marked installed in Model Center, bounded atom windows are grouped by the local LLM. Full chapters, books, and model-returned manuscript text are not accepted.
- Invalid LLM grouping is rejected and deterministic segments are kept with parser warnings.
- Cast Discovery runs after structure save. It creates high-confidence unique Character Bible records, verifies candidates against existing aliases, and leaves ambiguous candidates as review issues.
- Cast Review persists one speaker attribution per segment, leaves uncertain dialogue in a review queue, and uses approved character voice links during production unless a segment override is set.
- Parser warnings include code, review action, scope, text preview, offsets, evidence, and confidence.
- Structure quality metrics are available from `GET /api/v1/projects/{projectId}/structure/quality` and are written into `structure_manifest.json`.
- User-locked segments are carried forward across structure re-extraction.

## TTS And Rendering

The current TTS layer exposes a local provider registry through the dashboard.

- Mock TTS emits silent WAV files for validating the workflow.
- Managed Kokoro ONNX setup creates a local runtime, downloads model assets, builds a fixed preset voice registry, and verifies previews.
- Piper can be configured as a local CLI fallback with a local ONNX model and optional voice registry.
- XTTS-v2 is opt-in and requires a local Python runtime, reference WAV, language, and explicit reference-voice consent.
- Segment renders are immutable and stored under the project artifact store.
- Render cache keys are derived from segment text, synthesis text after pronunciation replacements, revision, resolved voice, resolved direction, output format, provider identity, and applied pronunciation entries.
- Direction Studio persists segment-level emotion, pace, intensity, pause, emphasis, and whisper controls. Each provider's `capabilities.direction` is truthful (see the capability matrix in [`tts-production-upgrade.md`](../pipeline/tts/tts-production-upgrade.md)): managed Kokoro transmits pace via the wrapper's `--speed` flag; Piper transmits pace natively; the custom Kokoro and XTTS-v2 adapters honor no engine-native direction. Unsupported controls are still recorded in metadata as `unsupportedDirection`.
- Chapter production records per-segment render queue rows and exposes latest-vs-parent render comparison for review.
- A cache hit returns the existing render; forced regeneration creates a new render linked to the prior render through `parent_render_id`.

## Local LLM

The local LLM layer uses Ollama only; there is no cloud fallback.

- Installed models are read from Ollama `/api/tags`.
- Model acquisition remains explicit through Model Center, which shells out to `ollama pull` for configured Ollama models.
- Extraction jobs call Ollama `/api/generate` with `stream: false` and a JSON schema passed through `format`.
- Responses are parsed and validated locally. Invalid JSON or schema mismatches fail closed after one retry.
- Embeddings call Ollama `/api/embed`.
- Each extraction writes prompt/response artifacts and an `llm_runs` row with status, schema, result, retry count, and error details.

## Review, QA, Assembly, And Export

Current QA is deterministic and technical.

- Segment and chapter QA can create durable issues for missing/corrupt audio, very short duration, duration mismatch, clipping, excessive silence, and render source mismatch.
- Chapter assembly orders successful segment renders by scene and segment order, writes a speech WAV, and records an immutable chapter render. The pipeline runs at **44.1 kHz mono PCM16**; segment renders at other rates are resampled (ffmpeg soxr at render time when available, else a numpy band-limited Fourier-method fallback during assembly). The numpy mix bus carries no per-sample Python loops.
- Each assembled chapter is mastered as the final step: **1000 ms / 2000 ms head/tail room tone** (pink-ish noise at ≈ -70 dBFS RMS, never digital silence) is always laid down, and when ffmpeg is present the deliverable is loudness-normalised to **-19 LUFS** and true-peak-limited to **-3 dBTP**. The manifest's `mastering` block records `targetLufs`, `truePeakDb`, `lra`, `mastered`, `roomToneMs`, and the `measured` stats. Without ffmpeg the un-mastered 44.1 kHz bed is written with `"mastered": false` and export readiness raises the `export_mastering` / `ffmpeg_missing` blocker (honest degradation).
- Ambience/music loops crossfade over 250 ms (equal-power) at each seam; ducking is a static -6 dB dip applied with 50 ms ramps.
- The pause inserted between two consecutive segments is `max(prev.pauseAfterMs, next.pauseBeforeMs, default_gap)`, where `default_gap` is 350 ms within a scene and 800 ms across a scene boundary (the scene boundary keeps its 800 ms floor). Pause values come from the direction that actually rendered each segment (its render `request_json`), clamped to the DirectionProfile 0–5000 ms bounds. The chapter render manifest's `pauses` block records `paragraphMs`, `sceneMs`, and an `applied` list of the per-gap `{afterSegmentId, ms}` actually written.
- Every "latest render/export" lookup selects by `created_at DESC, id DESC` (time-ordered, with the id as a tiebreaker); legacy rows without `created_at` sort oldest.
- Assembly refuses to stitch a segment render whose recorded request `revision` does not match the segment's current revision; the segment must be re-rendered first.
- Review patching can update segment text, render the affected segment, assemble a new chapter render, and record patch lineage.
- Export supports WAV and MP3 ZIP packages with a manifest and checksums.
- Open blocking issues prevent export.

## Stage 0 Regression Coverage

Stage 0 tests intentionally pin these current behaviors so later roadmap stages can safely replace them:

- page-marker pollution is removed before canonical normalization and recorded as applied clean-text decisions;
- suspicious OCR-like tokens are surfaced as review issues without mutating manuscript text;
- scanned and mixed PDF OCR paths are covered with mocked local OCR tools;
- render cache hits and forced render lineage remain append-only;
- export refuses open blocking review issues.
