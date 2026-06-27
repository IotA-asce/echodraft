# Current Pipeline Behavior

Document date: 2026-06-28

This document records the alpha pipeline behavior before the local-first roadmap stages deepen ingestion, cleaning, structure editing, local AI, casting, direction, QA, and export. It is intentionally descriptive, not aspirational.

## Ingestion

The current ingestion service accepts TXT, Markdown, DOCX, EPUB, and PDF files through `/api/v1/projects/{project_id}/source/import`.

- Source originals are copied into the project artifact store before parsing.
- Canonical text is written to `source/canonical/{source_id}.md` and copied to `source/canonical.md`.
- A source manifest is written under `manifests/source_manifest.{source_id}.json`.
- Normalization currently performs Unicode normalization, newline cleanup, smart-quote and dash conversion, adjacent duplicate paragraph removal, and unusually long paragraph warnings.
- HTML or Markdown page markers such as `<!-- Page 9 -->` are not removed yet. They remain in canonical text until the cleaning/canonicalization roadmap stage adds reviewable pollution removal.

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

- Chapters are detected from Markdown headings or simple `Chapter N` headings.
- If no chapter boundary is found, a single unresolved chapter is created.
- Scenes are detected from separator lines such as `***`, `---`, or `#`; otherwise the scene is unresolved.
- Segments are sentence-batched under `maxSegmentChars`.
- Basic speaker candidates are inferred from simple `Name said/asked/replied/whispered` patterns.
- Re-extraction currently replaces structure records and does not preserve future user locks.

## TTS And Rendering

The current TTS layer exposes mock audio and Kokoro setup paths through the dashboard.

- Mock TTS emits silent WAV files for validating the workflow.
- Managed Kokoro ONNX setup creates a local runtime, downloads model assets, builds a voice registry, and verifies previews.
- Segment renders are immutable and stored under the project artifact store.
- Render cache keys are derived from segment text, revision, voice, direction, output format, and adapter marker.
- A cache hit returns the existing render; forced regeneration creates a new render linked to the prior render through `parent_render_id`.

## Review, QA, Assembly, And Export

Current QA is deterministic and technical.

- Segment and chapter QA can create durable issues for missing/corrupt audio, very short duration, duration mismatch, clipping, excessive silence, and render source mismatch.
- Chapter assembly orders successful segment renders by scene and segment order, writes a speech WAV, and records an immutable chapter render.
- Review patching can update segment text, render the affected segment, assemble a new chapter render, and record patch lineage.
- Export supports WAV and MP3 ZIP packages with a manifest and checksums.
- Open blocking issues prevent export.

## Stage 0 Regression Coverage

Stage 0 tests intentionally pin these current behaviors so later roadmap stages can safely replace them:

- page-marker pollution currently survives ingestion normalization;
- scanned and mixed PDF OCR paths are covered with mocked local OCR tools;
- render cache hits and forced render lineage remain append-only;
- export refuses open blocking review issues.
