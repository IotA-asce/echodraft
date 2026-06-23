# Stage 01 — Manuscript ingestion

## Outcome

Import an authorized manuscript and create one canonical, traceable text representation with visible parsing warnings.

## Implement

- Define a `SourceDocument` model containing original filename, MIME type, checksum, import timestamp, rights declaration, parser version, and artifact path.
- Add importers for TXT, Markdown, DOCX, and EPUB. Normalize encoding, line endings, Unicode quotation marks, whitespace, and page/header noise while preserving source locations where possible.
- Implement `POST /api/v1/projects/{project_id}/source/import` as an asynchronous job. Reject unsupported files, empty text, oversized inputs, and imports without an affirmative rights declaration.
- Write the original file to `source/original/`; write canonical normalized text to `source/canonical.md`; and write `manifests/source_manifest.json` with checksums, importer metadata, and warnings.
- Model parser warnings with severity, source range, message, and suggested action. Examples: OCR corruption, unreadable EPUB section, duplicated header, or unusually long paragraph.
- Add `POST /api/v1/projects/{project_id}/source/reparse` to re-run normalization with a selected parser version without overwriting prior manifests.
- Build a UI import flow: rights confirmation, file selection/drop zone, progress state, source preview, warning list, and retry action.

## Validation

- Maintain fixtures for valid TXT, Markdown, DOCX, EPUB, malformed DOCX/EPUB, and OCR-noisy text.
- Test deterministic canonical output and manifest checksums for every valid fixture.
- Test that failed parsing leaves the original safely stored and records a failed job with actionable error details.

## Done when

A user can import TXT, DOCX, and EPUB, inspect normalized text and warnings, and repeat the import without corrupting the prior source artifact.
