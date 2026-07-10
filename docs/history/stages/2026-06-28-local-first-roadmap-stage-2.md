# Local-First Roadmap Stage 2 Implementation Plan

Goal: replace flat PDF extraction with page-aware PDF/OCR ingestion and import review metadata.

## Scope

- Add source page, OCR run/result, and canonical span tables.
- Store PDF page artifacts under the project artifact store.
- Extract embedded text per page.
- Render page images when Poppler is available.
- OCR low-quality pages with Tesseract when local OCR tools are available.
- Select the best text channel per page and preserve the choice in DB/artifacts.
- Expose source page review APIs and dashboard import review summaries.

## Implementation Notes

- Legacy direct `_extract_pdf()` behavior remains available for existing unit tests.
- Actual import jobs call the v2 path with source/project context.
- Text PDFs do not fail just because Poppler is missing; they import with page warnings and no image previews.
- OCR artifacts are structured JSON plus text, stored separately from canonical text.

## Validation

Run:

```bash
uv run pytest
uv run ruff check .
uv run mypy apps/api/src libs/db/src libs/domain-models/src
npm run web:typecheck
npm run web:lint
```

Expected result: all checks pass.
