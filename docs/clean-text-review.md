# Clean Text Review

Stage 3 adds deterministic cleaning before canonical manuscript normalization. The goal is to keep canonical text free of page-production artifacts while preserving review metadata for every automated decision.

## Pipeline Order

1. Source extraction reads TXT, Markdown, DOCX, EPUB, or selected PDF page text.
2. The cleaning pipeline removes deterministic pollution and records applied decisions.
3. Canonical normalization performs Unicode/newline cleanup, smart quote conversion, duplicate paragraph removal, and parser warnings.
4. Structure extraction reads only the cleaned canonical manuscript.

## Deterministic Changes

The cleaner currently applies:

- HTML page marker removal, such as `<!-- Page 9 -->`;
- explicit line page marker removal, such as `Page 9`, `[9]`, or `[Page 9]`;
- repeated running header/footer removal when form-feed page boundaries are present;
- simple line-break hyphenation repair;
- single-line wrap merging.

Applied changes are stored as `text_cleanliness_issues` with status `applied` and severity `info`.

## Review Findings

Suspicious OCR-like tokens are not changed automatically. They remain in canonical text and create open review issues:

- words containing digits, such as `rn0onlight`;
- repeated glyph words, such as `soooo`.

Reviewers can mark these findings resolved through `PATCH /api/v1/cleaning-issues/{issue_id}`. Resolution records the user decision but does not mutate canonical text.

## Artifacts And APIs

Cleaning manifests are stored under:

```text
{project_artifact_path}/sources/{source_id}/cleaning/cleaning_manifest.json
```

The API exposes:

- `GET /api/v1/sources/{source_id}`
- `GET /api/v1/sources/{source_id}/cleaning-runs`
- `GET /api/v1/sources/{source_id}/cleaning-issues`
- `PATCH /api/v1/cleaning-issues/{issue_id}`

The dashboard shows these records in Clean Text Review above PDF Import Review.

## Constraints

- Canonical text remains plain manuscript text.
- Page markers, OCR metadata, and review state stay in metadata/artifacts.
- Numeric chapter markers are preserved unless they are explicit page markers.
- User review status survives subsequent reads of the same imported source.
