# Structure Parser V2

Stage 4 upgraded structure extraction from a simple chapter/scene splitter into an evidence-backed parser with editorial controls. Structure Parser v3 keeps that deterministic pass and adds an optional local Ollama refinement pass.

## Parser Scope

The parser detects:

- front matter before the first chapter heading;
- Markdown chapter headings;
- `Chapter N`, prologue, epilogue, part, and book headings;
- explicit scene separators such as `***`, `---`, `####`, and `Scene N`;
- paragraph and sentence batches under the requested max segment size;
- dialogue segments from quoted text or `Name:` lines;
- performance beats from short bracketed or parenthetical lines.

After the deterministic pass, extraction checks whether the default local Ollama model is marked installed in Model Center. When it is available, Echodraft sends bounded windows of deterministic segments, not full chapters or books, to the local LLM. The LLM can split rough segments into narration, dialogue, and performance-beat subsegments with speaker hints and confidence. Invalid LLM output is discarded and the deterministic segment is kept with a warning.

When Ollama is not ready, deterministic extraction still completes and stores an informational warning that LLM refinement did not run.

## Warnings And Evidence

Each chapter, scene, and segment can carry `parserEvidence`. Parser warnings are stored separately in `structure_parser_warnings` with:

- scope type and scope ID;
- severity;
- message;
- evidence JSON;
- confidence;
- resolved state.

The dashboard shows parser warnings above the structure editor columns.

Segment evidence can include both `deterministic_parser` and `llm_segment_refinement` sources. LLM refinement evidence records the rough segment ID and local LLM run ID without changing canonical manuscript text.

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
