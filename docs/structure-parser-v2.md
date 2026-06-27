# Structure Parser V2

Stage 4 upgrades structure extraction from a simple chapter/scene splitter into an evidence-backed parser with editorial controls.

## Parser Scope

The parser detects:

- front matter before the first chapter heading;
- Markdown chapter headings;
- `Chapter N`, prologue, epilogue, part, and book headings;
- explicit scene separators such as `***`, `---`, `####`, and `Scene N`;
- paragraph and sentence batches under the requested max segment size;
- dialogue segments from quoted text or `Name:` lines;
- performance beats from short bracketed or parenthetical lines.

## Warnings And Evidence

Each chapter, scene, and segment can carry `parserEvidence`. Parser warnings are stored separately in `structure_parser_warnings` with:

- scope type and scope ID;
- severity;
- message;
- evidence JSON;
- confidence;
- resolved state.

The dashboard shows parser warnings above the structure editor columns.

## Editorial Controls

The API supports:

- chapter metadata updates;
- scene metadata updates;
- structure locks for chapters, scenes, and segments;
- segment split;
- adjacent segment merge.

Locked segments are carried forward during re-extraction so approved editorial splits or text survive parser reruns.

## Constraints

- Segment remains the smallest editable, renderable, reviewable, and patchable unit.
- Parser warnings and evidence stay in metadata, not in canonical manuscript text.
- Split and merge operations mark affected segments for review.
- Locked segments can still be explicitly unlocked by the user.
