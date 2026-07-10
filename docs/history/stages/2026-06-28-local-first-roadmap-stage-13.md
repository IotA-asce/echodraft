# Stage 13: Export Polish

Branch: `codex/stage-13-export-polish`

## Implemented Scope

- Added enriched `ExportRequest`, `ExportPackage`, `ExportBlocker`, and `ExportEstimate` contracts.
- Added `POST /api/v1/projects/{projectId}/exports/estimate` for preflight blockers and estimated package size.
- Added `audioVariant` selection for `active`, `clean`, and `mixed` chapter audio.
- Added metadata fields for title, author, album, publisher, copyright, language, and cover image path.
- Enriched `export_manifest.json` with source metadata, readiness/QA summary, output checksums, render lineage, provider/model/voice summaries, estimated size, archive size, and archive checksum.
- Updated the dashboard export card with audio variant selection, metadata fields, richer export history rows, and a disabled `M4B planned` marker.
- Kept M4B fail-closed with an explicit planned blocker until a media adapter exists.

## Architecture Notes

- No export DB migration was needed. The relational table remains path/status metadata; detailed provenance stays in the filesystem manifest.
- Export blockers are deterministic and local. The API does not attempt cloud conversion or cloud metadata enrichment.
- Mixed export selection requires an existing mixed chapter render. Clean export always uses the narration stem.

## Validation Plan

- `uv run pytest`
- `uv run ruff check .`
- `uv run mypy apps/api/src libs/db/src libs/domain-models/src`
- `npm run web:typecheck`
- `npm run web:lint`
- `npm run web:test:smoke` when the existing local API port conflict is cleared
