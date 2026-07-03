# PDF OCR Ingestion

Document date: 2026-06-28

Stage 2 introduces page-aware PDF ingestion. The canonical manuscript remains a clean text artifact, while page extraction details are stored separately for review and future correction workflows.

## Artifact Layout

For a PDF source, Echodraft writes page artifacts under:

```text
.echodraft/projects/{project_id}/sources/{source_id}/pdf/
  original.pdf
  pages/
    page_0001.png
  embedded_text/
    page_0001.txt
  selected_text/
    page_0001.txt
  ocr/
    run_{ocr_run_id}/
      page_0001.txt
      page_0001.json
  manifests/
    ingestion_manifest.json
```

Page images are created when Poppler is available. Text-first PDFs still import without Poppler; the page record stores a warning that previews require Poppler.

## Database Records

Stage 2 adds:

- `source_pages` for page number, image path, embedded text path, selected text path, extraction method, confidence, and warnings;
- `ocr_runs` for OCR provider runs;
- `ocr_page_results` for per-page OCR text/JSON artifacts;
- `canonical_spans` for page-to-canonical offset mapping.

## Channel Selection

Each PDF page is evaluated independently.

- Embedded text is selected when it has enough words and no obvious extraction-quality signals.
- OCR is selected when embedded text is too sparse or suspicious and local OCR succeeds.
- If Poppler is not available, clean embedded-text PDFs still import and retain an actionable page warning.

The selected page text is what feeds canonical text normalization. Page numbers, images, OCR metadata, and confidence details remain outside canonical manuscript text.

## API

Import review uses:

- `GET /api/v1/sources/{source_id}/pages`
- `GET /api/v1/sources/{source_id}/pages/{page_number}`

Responses include extraction method, confidence, warnings, selected text preview, artifact paths, and image URL when a page render exists.
