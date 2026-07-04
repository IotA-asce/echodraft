# Export Polish

Stage 13 upgrades export packaging while keeping export artifacts local and manifest-driven.

## Formats

- `wav`: supported as a ZIP package of chapter audio plus `export_manifest.json`.
- `mp3`: supported as a ZIP package using local FFmpeg with MP3 support. Chapter MP3s are tagged with title, artist, album, audiobook genre, track number, language, and optional publisher/copyright metadata; a supplied cover is embedded as attached artwork and also copied into the package.
- `m4b`: supported as a single chapter-marked AAC audiobook file (`audiobook.m4b`) inside the ZIP. FFmpeg consumes a concat manifest plus FFMETADATA chapter blocks, writes audiobook metadata, and attaches cover art when supplied.

MP3 and M4B exports require local FFmpeg. Without FFmpeg, preflight returns an explicit `ffmpeg_missing` blocker.

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

## Retail sample

Requests may set `includeRetailSample: true` for `mp3` or `m4b` exports. Export writes `retail_sample.mp3` from the first up-to-300 seconds of the first selected chapter, at 192 kbps, with the same audiobook ID3 metadata minus chapter track numbering. WAV exports ignore the sample flag.

## Preflight Estimate

`POST /api/v1/projects/{projectId}/exports/estimate` returns:

- selected chapter count
- estimated package size
- normalized metadata
- export blockers
- legacy `m4bPlanned` status, now always `false` for supported M4B exports

Blockers include rights issues, open blocking review issues, missing chapter renders, missing mixed renders, missing audio files, missing FFmpeg for MP3/M4B/sample exports, missing cover image paths, unsupported formats, and empty chapter selection.

## Manifest

Successful exports write `export_manifest.json` with:

- `schemaVersion: "0.3.0"`
- source document metadata and checksum
- latest readiness report summary
- open blocking issue summary
- output files, bytes, duration, and SHA-256 checksums
- a QA scorecard for each output file
- package-relative `artifactPath` and local `artifactUrl` values for each output file, including the M4B audiobook and retail sample
- chapter render IDs and selected audio variant
- segment render lineage from chapter manifests
- provider/model/voice summary
- archive bytes and archive SHA-256 in the filesystem manifest

The manifest `qa` block contains:

- `targetLufs: -19.0`
- `lufsTolerance: 1.0`
- `truePeakCeilingDb: -3.0`
- `allWithinTolerance`
- `outputs[]` entries with `filename`, `method`, `durationMs`, `bytes`, `sha256`, optional `lufsIntegrated`, optional `truePeakDb`, and `withinTolerance`
- latest readiness and open blocking issue summaries

The export table stores package paths and status only. Detailed provenance stays in the manifest; audio blobs stay in artifacts.
