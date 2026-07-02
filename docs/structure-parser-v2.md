# Structure Parser

Stage 03 now uses `structure-parser-0.4.0`, a deterministic structure compiler with optional local atom grouping. The parser keeps the system local-first and source-preserving: canonical text is compiled into blocks, chapters, scenes, atoms, renderable segments, cast hints, quality metrics, and reviewable warnings without adding parser tables.

## Parser Scope

The compiler runs these passes:

- block map with source offsets and line ranges;
- scored chapter candidates, including front matter and `Chapter One` plus title-line handling;
- scored scene candidates from explicit separators and conservative inferred breaks;
- quote-aware atomization for straight and curly quotes with apostrophe safety;
- atom-window speaker resolution for colon speakers, quote/tag pairs, inverted tags, action beats, and unresolved dialogue;
- segment building from source-ordered atoms while preserving offsets;
- cast discovery and speaker attribution from parser evidence.

Segments remain DB-compatible as `narration`, `dialogue`, or `performance_beat`. Richer production types such as `dialogue_with_tag`, `action_beat`, and `heading` are stored in `parserEvidence.productionType`.

After the deterministic pass, extraction checks whether the default local Ollama model is marked installed in Model Center. When available, Echodraft sends bounded atom windows and nearby context snippets to the local LLM. The response schema returns atom IDs only, never manuscript text. Validation requires exact atom coverage, adjacency, source order, known IDs, allowed production types, and safe speaker hints.

When Ollama is unavailable or invalid output is returned, deterministic atom-built segments are kept and a scoped diagnostic warning is stored.

## Warnings And Evidence

Each chapter, scene, and segment can carry `parserEvidence`. Parser warnings are stored separately in `structure_parser_warnings` with:

- code and review action;
- scope type and scope ID;
- severity;
- message;
- evidence JSON with text preview, offsets, and confidence where available;
- confidence;
- resolved state.

The dashboard shows parser warnings above the structure editor columns and shows segment-level parser evidence below each segment.

Segment evidence records sources such as `block_map`, `quote_aware_atomization`, `deterministic_segment_builder`, and `optional_atom_llm_grouping`. LLM refinement evidence records the local LLM run ID and atom IDs without accepting model-returned manuscript text.

Stable source-span IDs are used for chapters, scenes, segments, atoms, and offset-backed warnings:

```text
sha1("{source_id}:{start}:{end}:{text}")[:16]
```

UUID fallback is reserved for cases where offsets are unavailable.

## Quality Reporting

`GET /api/v1/projects/{projectId}/structure/quality` returns the current structure quality summary, including chapter, scene, segment, dialogue, unresolved-dialogue, long-segment, warning, cast-candidate, and LLM refinement counts.

The same metrics are written into `structure_manifest.json` under `payload.quality`.

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
