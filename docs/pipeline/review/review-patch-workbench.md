# Review & Patch Workbench

Stage 12 upgrades segment review from a simple issue list into a layered inspector. The workbench is still segment-first: selecting `Inspect` on a segment loads source text, canonical text, parser evidence, cast, direction, render history, waveform metadata, QA issues, comments, and patch attempts for that one segment.

## API

`GET /api/v1/projects/{projectId}/segments/{segmentId}/review-inspector`

The response is a `SegmentReviewInspector` read model. It is assembled from existing local metadata and artifacts:

- structure records and parser warnings from SQLite
- current source/canonical segment text from the `segments` table
- speaker attribution and voice link from Cast Review data
- saved direction profile from `segment_directions`
- immutable segment render rows from `segment_renders`
- waveform and duration data from the latest render metadata JSON
- review issues, comments, and patch attempts from review tables

No audio blobs or waveform blobs are stored in the relational database. The API returns artifact URLs for segment render audio using the same local artifact route as the render history endpoint.

## Dashboard Behavior

The dashboard’s segment action is now `Inspect`. It loads the existing render comparison and the inspector read model together. The Review & Patch section shows compact layers for:

- Source and canonical text
- Structure and parser warning summary
- Cast attribution and linked voice status
- Direction emotion, pace, intensity, and lock/source metadata
- Current segment audio and waveform metadata
- Render history, QA findings, comments, and patch queue

Patch attempts remain append-only. A patch creates a new segment render, records the previous render as the parent, reassembles the owning chapter, and adds a `patch_attempts` row. Segment text edits continue to create revisions and stale only the affected segment render fingerprint.

`POST /api/v1/projects/{projectId}/segments/{segmentId}/patch` accepts an optional `voiceProfileId` and `direction`; omitted fields are resolved server-side using the same layering as production (segment override → cast-resolved voice for approved speaker attributions → project narrator voice; direction override → saved segment direction → project default → a blank profile). Any voice/direction the caller does supply is honored as a manual override for that field. Patch always renders with `force=true`: it re-renders with the segment's resolved voice and direction and always produces fresh audio, so the render cache can never silently return stale audio for a patch.

## Validation

Stage 12 tests cover:

- inspector response layers after render, issue, comment, and patch workflows
- waveform metadata loaded from local render metadata
- patch queue lineage after selective patching
- segment revision staling only the edited segment in a multi-segment chapter
