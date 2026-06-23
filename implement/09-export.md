# Stage 09 — Export and packaging

## Outcome

Produce validated, shareable chaptered audio outputs and an auditable export manifest.

## Implement

- Define `ExportJob` and `ExportPackage` records with source chapter-render IDs, requested format/settings, metadata, cover art, output paths, checksums, and validation result.
- Support WAV, MP3, and M4B. Keep codec and container implementation behind a media-export adapter so missing local capabilities fail clearly.
- Build export input validation: source renders exist, no blocking review issues, requested metadata is valid, artwork is safe, and required audio tools are available.
- Implement chapter splitting, stable filenames, metadata tags (title, author, narrator, series, chapter, year), cover art placeholders, and output directory selection.
- Write `manifests/export_manifest.json` with the exact source renders, codecs, bitrate/sample rate, metadata, checksums, and tool versions.
- Add UI for format selection, quality settings, metadata editing, output preview, job progress, error display, and reveal-in-folder action.
- Validate finished files by reopening them with a media inspector and comparing duration/checksum expectations.

## Validation

- Test each format with deterministic fixture audio and verify tags, chapter ordering, output naming, and failure reporting.
- Test invalid artwork, unsupported codecs, missing source renders, and cancellation without partial packages being marked successful.
- Perform a manual export of a sample chapter in WAV and MP3; include M4B when the local toolchain supports it.

## Done when

A reviewed chaptered draft can be exported as WAV, MP3, or M4B with correct metadata, validated output files, and a complete export manifest.
