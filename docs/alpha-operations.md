# Alpha Operations

## Recovery

- Jobs interrupted by an application restart are marked failed; restart the workflow from its persisted source, render, or chapter artifact.
- Chapter production runs expose per-segment progress in the dashboard. Retry a failed chapter after correcting its local adapter, narrator selection, or source segment; valid prior renders are retained.
- Validation errors require correcting the request. Filesystem errors require checking local disk capacity and permissions.
- Do not include manuscript text or generated audio in bug reports unless the tester explicitly consents.

## Triage

Use `blocking` for an inability to import, render, assemble, patch, or export. Include reproduction steps, job ID, app version, and the redacted error message.

## Known Limits

- In-process jobs cannot resume mid-operation.
- MP3 export requires local FFmpeg with an MP3 encoder. M4B remains unsupported.
- Ambience asset mixing remains intentionally deferred; speech-only output is the stable alpha path.
- Mock TTS is intentionally silent. Current Kokoro support validates a local wrapper and applies the selected voice ID, but direction controls are retained as manifest notes and may not alter synthesis.
- Text PDFs import directly. Scanned PDFs require `pdftoppm` from Poppler and English Tesseract data on `PATH`; OCR runs locally at 200 DPI and is capped at 150 low-text pages per import.
