# Structure Parser

Stage 03 now uses `structure-parser-0.4.0`, a deterministic structure compiler with optional local atom grouping. The parser keeps the system local-first and source-preserving: canonical text is compiled into blocks, chapters, scenes, atoms, renderable segments, cast hints, quality metrics, and reviewable warnings without adding parser tables.

## Parser Scope

The compiler runs these passes:

- block map with source offsets and line ranges;
- container chapter-signal promotion: chapter signals recovered at ingestion from
  DOCX heading styles and EPUB spine/TOC (`source_manifest.payload.structureSignalsPath`
  → `chapter_signals.json`) are matched to parsed blocks by case-insensitive,
  whitespace-collapsed **anchor text** (never raw offsets, which cleaning shifts).
  A matched block is promoted to a chapter boundary bypassing `EXPLICIT_CHAPTER_RE`,
  with `parserEvidence.reason` set to the signal's `sourceKind` (`docx_heading` /
  `epub_toc` / `epub_spine`). Only `level <= 1` signals promote a chapter (`Title`
  level 0, `Heading 1` level 1); `Heading 2` (level 2) is a scene-break hint only.
  A signal matching no block emits a `container_signal_unmatched` warning instead
  of failing. Regex detection still runs; a block promoted by both keeps the
  container reason;
- scored chapter candidates, including explicit front matter/back matter
  headings and `Chapter One` plus title-line handling;
- scored scene candidates from explicit separators and conservative inferred breaks;
- document-level and per-chapter language detection stored in quality and chapter
  `parserEvidence`;
- quote-aware atomization for straight and curly quotes with apostrophe safety,
  including conservative multi-paragraph dialogue spans;
- atom-window speaker resolution for colon speakers, quote/tag pairs, inverted tags, action beats, and unresolved dialogue;
- footnote-like paragraph routing into reviewable `footnote` production segments;
- segment building from source-ordered atoms while preserving offsets, preferring
  paragraph, sentence, and dialogue-tag boundaries with a clause-level prosody
  fallback for overlong sentences;
- cast discovery and speaker attribution from parser evidence.

Segments remain DB-compatible as `narration`, `dialogue`, or `performance_beat`. Richer production types such as `dialogue_with_tag`, `action_beat`, `footnote`, and `heading` are stored in `parserEvidence.productionType`.

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

The dashboard shows parser warnings and open cast discovery review issues above the structure editor columns, with filters for speaker, scene, mixed/long segment, cast, LLM, and error categories. Segment-level parser evidence remains visible below each segment.

Segment evidence records sources such as `block_map`, `quote_aware_atomization`, `deterministic_segment_builder`, and `optional_atom_llm_grouping`. Deterministic segment evidence also records atom kinds and atom reasons, including `multi_paragraph_dialogue`, `footnote_routed`, and `prosody_clause_split` when those rules fire. LLM refinement evidence records the local LLM run ID and atom IDs without accepting model-returned manuscript text.

Review hardening warnings include unclosed quotes, atom offset validation failures, footnote routing, mixed narration/dialogue segments, multiple-speaker segments, ambiguous two-person exchanges, unresolved dialogue, possible scene breaks, and LLM diagnostics. Footnote-like paragraphs stay as narration-compatible segments with `parserEvidence.productionType = "footnote"`, `status = "needs_review"`, and `reviewAction = "inspect_footnote"`. Offset validation failures include structured errors plus uncovered and overlapping source ranges. Cast duplicate and low-confidence candidate reviews remain review issues with structured metadata codes and are shown in the Story Map review panel.

Cast evidence graphs distinguish speaker evidence from deterministic mention evidence. Mentions are counted only for candidates already discovered through speaker or LLM evidence, and never create cast candidates by themselves.

Stable source-span IDs are used for chapters, scenes, segments, atoms, and offset-backed warnings:

```text
sha1("{source_id}:{start}:{end}:{text}")[:16]
```

UUID fallback is reserved for cases where offsets are unavailable.

## Quality Reporting

`GET /api/v1/projects/{projectId}/structure/quality` returns the current structure quality summary, including chapter, `chaptersFromContainerSignals`, scene, segment, dialogue attribution, unresolved-dialogue, duplicate-cast, offset-validation, unclosed-quote, long-segment, warning, cast-candidate, detected-language, and LLM refinement counts.

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
