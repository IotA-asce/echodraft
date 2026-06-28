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

The structure service reads the latest canonical source and replaces the project chapter/scene/segment hierarchy.

- Chapters are detected from Markdown headings, `Chapter N`, prologue/epilogue, part, and book headings.
- Text before the first chapter heading is represented as front matter.
- If no chapter boundary is found, a single unresolved chapter is created with a parser warning.
- Scenes are detected from separator lines such as `***`, `---`, `####`, or `Scene N`; otherwise a single inferred scene is created with a confidence note.
- Segments are paragraph/sentence-batched under `maxSegmentChars`, with dialogue and performance-beat segment types.
- Basic speaker candidates are inferred from `Name said/asked/replied/whispered` and `Name:` patterns.
- Cast Review persists one speaker attribution per segment, leaves uncertain dialogue in a review queue, and uses approved character voice links during production unless a segment override is set.
- Parser warnings include scope, evidence, and confidence.
- User-locked segments are carried forward across structure re-extraction.

## TTS And Rendering

The current TTS layer exposes a local provider registry through the dashboard.

- Mock TTS emits silent WAV files for validating the workflow.
- Managed Kokoro ONNX setup creates a local runtime, downloads model assets, builds a voice registry, and verifies previews.
- Piper can be configured as a local CLI fallback with a local ONNX model and optional voice registry.
- XTTS-v2 is opt-in and requires a local Python runtime, reference WAV, language, and explicit reference-voice consent.
- Segment renders are immutable and stored under the project artifact store.
- Render cache keys are derived from segment text, synthesis text after pronunciation replacements, revision, resolved voice, resolved direction, output format, provider identity, and applied pronunciation entries.
- Direction Studio persists segment-level emotion, pace, intensity, pause, emphasis, and whisper controls; current Kokoro adapters apply supported pace data and retain unsupported controls in metadata.
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
- Chapter assembly orders successful segment renders by scene and segment order, writes a speech WAV, and records an immutable chapter render.
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
