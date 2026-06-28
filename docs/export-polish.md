# Export Polish

Stage 13 upgrades export packaging while keeping export artifacts local and manifest-driven.

## Formats

- `wav`: supported as a ZIP package of chapter audio plus `export_manifest.json`.
- `mp3`: supported as a ZIP package using local FFmpeg with MP3 support.
- `m4b`: planned. The API and UI explicitly report M4B as planned until a media adapter is implemented.

## Audio Variant

Export requests accept `audioVariant`:

- `active`: use the active chapter assembly path. Mixed audio is used when available, otherwise clean narration.
- `clean`: use the clean speech stem even if a mixed render exists.
- `mixed`: require a mixed chapter render. Export estimate reports a blocker if the chapter only has clean narration.

## Metadata

Export requests accept cover and package metadata fields:

- `title`
- `author`
- `album`
- `publisher`
- `copyright`
- `language`
- `coverImagePath`

Cover paths remain local filesystem paths. If supplied, the cover file is copied into the export staging directory and included in the ZIP.

## Preflight Estimate

`POST /api/v1/projects/{projectId}/exports/estimate` returns:

- selected chapter count
- estimated package size
- normalized metadata
- export blockers
- M4B planned status

Blockers include rights issues, open blocking review issues, missing chapter renders, missing mixed renders, missing audio files, missing FFmpeg for MP3, missing cover image paths, unsupported formats, and empty chapter selection.

## Manifest

Successful exports write `export_manifest.json` with:

- source document metadata and checksum
- latest readiness report summary
- open blocking issue summary
- output files, bytes, duration, and SHA-256 checksums
- chapter render IDs and selected audio variant
- segment render lineage from chapter manifests
- provider/model/voice summary
- archive bytes and archive SHA-256 in the filesystem manifest

The export table stores package paths and status only. Detailed provenance stays in the manifest; audio blobs stay in artifacts.
