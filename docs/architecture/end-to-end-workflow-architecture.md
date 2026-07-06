# End-to-End Workflow Architecture

Document date: 2026-07-07

This document is the single architecture entry point for the Echodraft local audiobook workflow. It consolidates the import, clean-text, structure, cast, direction, voice, render, review, patch, and export stages, then analyzes the most recent completed Structure & Cast Draft run for project `proj_853c19aa7bbb4706`.

## Architecture Goals

Echodraft is a local-first, segment-oriented audiobook production system. Its architecture is optimized for:

- **local privacy:** source manuscripts, prompts, generated audio, manifests, and review data stay on the machine;
- **segment atomicity:** the segment is the smallest editable, renderable, reviewable, and patchable unit;
- **manifest-driven stages:** every major pipeline step writes structured metadata and diagnostics;
- **review-safe automation:** uncertain parser, cast, speaker, direction, audio, and export decisions become reviewable evidence instead of silent guesses;
- **patchability:** fixing one weak line should not require regenerating the whole book;
- **honest degradation:** missing local tools, invalid LLM output, stale renders, and interrupted jobs must be visible.

## System Components

```text
Next.js dashboard
  -> FastAPI API
     -> service layer: ingestion, structure, casting, direction, rendering, QA, export
        -> SQLite repositories for durable metadata and review state
        -> local filesystem artifact store for source, manifests, prompts, WAVs, exports
        -> local tools: Poppler, Tesseract, Ollama, ffmpeg, Kokoro/Piper/XTTS adapters
```

### Frontend

The dashboard is a workflow shell rather than a generic file browser. It exposes these primary steps:

1. Project and rights setup.
2. Voice engine setup.
3. Manuscript intake.
4. Structure and cast draft.
5. Voice Bible and cast review.
6. Direction Studio.
7. Chapter production.
8. Review and patch.
9. Readiness QA.
10. Export.

The UI tracks background jobs through `/api/v1/jobs/{jobId}` and, after the latest job-status fix, can rediscover project jobs with `/api/v1/projects/{projectId}/jobs`. This matters because local structure and render jobs can outlive a browser session.

### Backend

The FastAPI app owns orchestration. Most domain behavior lives in service modules rather than route handlers:

- ingestion and PDF/OCR normalization;
- structure parsing and optional atom-level local LLM grouping;
- cast discovery and speaker attribution;
- direction inference;
- voice setup and TTS preview/rendering;
- chapter production and assembly;
- review, QA, patching, and export.

The backend uses a bounded in-process job runner. Jobs are durable rows, but running work is not resumable after API restart. On startup, interrupted jobs are marked failed with an explicit restart message.

### Persistence

SQLite stores project metadata, jobs, structure rows, cast rows, speaker attributions, directions, render records, issues, comments, approvals, and export metadata.

The filesystem stores large and inspectable artifacts:

- original source files;
- PDF page extraction/OCR artifacts;
- canonical text;
- source and structure manifests;
- local LLM prompt/response files;
- segment and chapter WAV files;
- export packages and manifests.

This split keeps the database queryable while avoiding audio/source blobs in relational tables.

## Pipeline Stages

### 1. Project and Rights

A project starts with a declared rights status. The project artifact directory is created before the row is committed; if creation fails, the partially created artifact directory is removed.

Primary durable outputs:

- `projects`;
- rights declaration;
- project artifact layout.

### 2. Source Import

The source import endpoint accepts TXT, Markdown, DOCX, EPUB, and PDF.

For PDFs, import is page-aware:

- embedded text is extracted per page where readable;
- low-text pages are rendered with Poppler and OCRed with Tesseract when available;
- per-page extraction metadata, selected text, page warnings, and approximate canonical spans are persisted.

The source is normalized into canonical text after deterministic cleaning. Cleaning removes common page-marker pollution, repairs simple line-wrap and hyphenation artifacts, applies Unicode/newline normalization, and records suspicious OCR-like text for review rather than mutating it away.

Primary durable outputs:

- `source_documents`;
- source page metadata;
- canonical text file;
- source manifest;
- clean-text decisions and issues.

### 3. Structure Extraction

Structure extraction reads the latest canonical source and replaces the project hierarchy. It is a compiler pipeline:

```text
canonical text
  -> block map with offsets
  -> chapter candidates
  -> scene candidates
  -> quote-aware atoms
  -> renderable segments
  -> optional local LLM atom grouping
  -> cast discovery
  -> speaker attribution
  -> quality metrics and warnings
```

Chapters can come from Markdown headings, explicit chapter/prologue/epilogue patterns, and container signals from DOCX/EPUB. Scenes come from explicit separators and conservative inferred breaks. Segments remain DB-compatible as `narration`, `dialogue`, or `performance_beat`, while richer production labels live in `parserEvidence`.

Optional local LLM grouping is deliberately constrained:

- only bounded atom windows are sent;
- full books and full chapters are not sent;
- the response may return atom IDs and labels, not generated manuscript text;
- validation requires exact atom coverage, adjacency, known IDs, source order, and allowed production types;
- invalid output is rejected and deterministic segments are kept.

Primary durable outputs:

- chapters, scenes, segments;
- segment parser evidence;
- structure warnings;
- `structure_manifest.json`;
- structure quality metrics.

### 4. Cast Discovery

Cast Discovery runs after structure extraction. It uses parser speaker evidence, bounded scene and structure extraction windows, a durable character mention ledger, shortlist-first dedupe, automated cast graph decisions, alias matching, and confidence gates.

The mention ledger is the durable evidence layer for observed names, aliases, titles, pronouns, and supporting source references. Extraction passes append new observations and recompute cast decisions without discarding prior confirmed evidence. Deduplication is shortlist-first: the system evaluates the strongest candidate matches before it opens possible-duplicate review, which keeps noisy long-tail candidates from exploding into pairwise review volume.

High-confidence unique candidates become Character Bible rows. High-confidence duplicate outcomes can merge automatically when the shortlist is unambiguous and prior project rulings agree. Ambiguous, duplicate-looking, or low-confidence candidates still become review issues. Internal character enrichment is additive: new evidence can extend aliases, traits, or role notes without overwriting user locks or canonical text.

Primary durable outputs:

- characters;
- durable character mention ledger rows;
- cast graph decisions and remembered duplicate rulings;
- cast discovery review issues;
- `casting_manifest.json`.

### 5. Speaker Attribution

Speaker attribution writes one row per segment. It combines:

- explicit parser candidates;
- character-name and alias matches;
- nearby dialogue turn evidence;
- speech-action cues;
- pronoun-coreference cues when character traits support it;
- two-speaker active-scene exchange rules;
- interruption and vocative exchange rules;
- conservative alternation hints;
- optional bounded local LLM attribution.

Speaker attribution consumes the Character Bible and cast graph state produced by Cast Discovery. Cast extraction stays bounded to structure and scene windows; attribution stays bounded to scene windows. When attribution finds strong evidence for an already-known character, it can feed additive internal enrichment back into the cast graph without replacing user-owned data.

Review safety rules:

- locked rows are never overwritten;
- unknown dialogue remains visible;
- deterministic inferred rows stay `needs_review` unless they are explicit/high-confidence matches;
- LLM output is accepted only for target segment IDs, not context-only IDs;
- local LLM failures create review issues instead of blocking the whole job.

Primary durable outputs:

- `speaker_attributions`;
- evidence JSON with rule names, active speaker rosters, LLM run IDs, confidence, and window IDs;
- speaker/cast review issues;
- `casting_manifest.json` updates for downstream production inputs.

### 6. Direction

Direction inference creates or updates segment delivery controls:

- pace;
- intensity;
- tone;
- emotion;
- pauses;
- emphasis;
- whisper;
- no-SFX flag;
- style prompt metadata.

Deterministic inference is the default. Optional local LLM direction inference uses bounded scene windows and stores evidence. User-locked direction rows are not overwritten.

Primary durable outputs:

- `segment_directions`;
- direction evidence and fingerprints.

### 7. Voice and TTS

Voice setup is local-provider based:

- `mock` validates the workflow with silent audio;
- managed Kokoro ONNX can install and use a local resident worker;
- Piper and XTTS-v2 remain local adapter paths;
- no cloud fallback is introduced.

Production resolves segment voice in this order:

1. segment-level voice override;
2. approved speaker attribution linked to a character voice;
3. project narrator voice.

Render cache keys include text, revision, resolved voice, direction, provider identity, output format, and pronunciation entries. This lets unchanged segments reuse audio while changed segments get new lineage.

Primary durable outputs:

- voice profiles;
- pronunciation entries;
- immutable segment renders;
- render queue rows;
- render manifests.

### 8. Chapter Production and Assembly

Chapter production renders missing/stale segments and records progress. Assembly orders successful segment renders by scene and segment order, inserts direction-driven pauses, optionally mixes ambience/music/SFX, and writes chapter WAV artifacts.

The current pipeline writes 44.1 kHz mono PCM16 chapter audio. ffmpeg, when available, is used for resampling/loudness measurement/mastering support. Missing ffmpeg is visible in readiness/export checks.

Primary durable outputs:

- segment render rows;
- chapter render rows;
- assembly manifests;
- audio artifacts.

### 9. Review, Patch, QA, and Approval

Review is designed around targeted correction:

- inspect transcript, speaker, direction, waveform, issues, and render lineage for one segment;
- edit one line;
- rerender only the affected segment;
- reassemble the chapter;
- preserve parent-child render history.

Readiness QA checks text, structure, speaker attribution, voices, direction, render freshness, audio health, ASR verification where available, approvals, scoped blockers, and export readiness.

Primary durable outputs:

- issues;
- comments;
- patch attempts;
- readiness reports;
- chapter approvals.

### 10. Export

Export packages approved/current chapter renders into WAV/MP3/M4B outputs where supported. The export manifest records metadata, checksums, source/render lineage, output roles, QA measurements, and blockers.

Open blocking issues prevent export.

Primary durable outputs:

- export package rows;
- ZIP/audio outputs;
- export manifest and QA summary.

## Evidence and Warning Taxonomy

The system currently stores two kinds of human-attention items:

- **structure warnings:** parser and attribution warnings attached to chapter, scene, or segment scopes;
- **issues:** durable review queue items, including cast discovery, QA, export blockers, and workflow-specific findings.

This distinction is architecturally useful but currently too blunt in the UI. A large project can produce thousands of segment-level warnings that are technically accurate but not actionable one by one. The architecture should treat high-volume findings as grouped work packages.

Recommended warning groups:

- source quality problems: OCR, page noise, front/back matter, long paragraphs;
- structural boundary problems: chapter/scene under-detection, false scene breaks;
- segmentation problems: long segments, mixed dialogue/narration, unclosed quotes;
- cast graph problems: duplicate candidates, low-confidence names, noisy entities;
- speaker attribution problems: unresolved dialogue, low-confidence rows, alternation review;
- LLM diagnostics: invalid grouping, skipped windows, schema failures;
- production blockers: missing voice, stale render, corrupt audio, unapproved chapter.

## Last Completed Job Analysis

This section analyzes the most recent completed Structure & Cast Draft run for:

- project: `proj_853c19aa7bbb4706`
- source: `Project Mary Hail.pdf`
- source id: `src_b3d453af2ac64deb`
- latest successful structure job: `job_3c8fbf0189cd4c8e`
- captured on: 2026-07-06

### Job Timeline

| Job ID                 | Status    | Started             | Finished            | Final progress                          |
| ---------------------- | --------- | ------------------- | ------------------- | --------------------------------------- |
| `job_3c8fbf0189cd4c8e` | succeeded | 2026-07-05 18:36:10 | 2026-07-06 01:33:29 | `speaker_attribution` `6995/6995`       |
| `job_713bc65b90064695` | failed    | 2026-07-05 18:06:21 | 2026-07-05 18:30:14 | interrupted during `llm_cast_discovery` |
| `job_82693b33bfef4e7f` | failed    | 2026-07-05 18:00:06 | 2026-07-05 18:03:29 | interrupted during `llm_cast_discovery` |
| `job_bb951ee9645947a8` | failed    | 2026-07-05 17:24:39 | 2026-07-05 17:53:37 | interrupted during `llm_cast_discovery` |

The successful job ran for roughly 6 hours 57 minutes. The earlier failed jobs were marked interrupted after API/process restarts, which is expected for the current in-process job architecture.

### Source Import Signals

The source import succeeded but contained quality signals that likely affected downstream structure and casting:

| Source warning                                   | Count |
| ------------------------------------------------ | ----: |
| Unusually long paragraph detected                |    99 |
| Text was extracted with local OCR                |    18 |
| No readable text was found after local OCR       |     1 |
| Canonical cleaning applied deterministic changes |     1 |

The cleaning pass reported `15745` deterministic changes. That does not mean the source failed, but it does indicate the PDF required substantial normalization. A scanned/mixed PDF with long paragraphs and OCR pages is a risk factor for chapter detection, quote closure, and cast extraction.

### Structure Quality Output

| Metric                             |     Value |
| ---------------------------------- | --------: |
| Chapters                           |         5 |
| Chapters from container signals    |         0 |
| Scenes                             |         8 |
| Segments                           |      6995 |
| Dialogue segments                  |      3425 |
| Dialogue attribution coverage      |      7.0% |
| Unresolved dialogue                |      3184 |
| Average segment length             | 117 chars |
| Long segments                      |         4 |
| Mixed segment warnings             |         0 |
| Cast candidates                    |       601 |
| Possible duplicate cast candidates |       435 |
| Low-confidence cast candidates     |       125 |
| Possible scene breaks              |         4 |
| Offset validation failures         |         0 |
| Unclosed quotes                    |        74 |
| Detected language                  |      `en` |
| Language confidence                |      0.41 |
| Warnings needing review            |      3363 |
| LLM refinement used                |      true |
| LLM accepted batches               |         4 |
| LLM rejected batches               |         4 |

### Warning Breakdown

| Warning                                                  | Count | Interpretation                                           |
| -------------------------------------------------------- | ----: | -------------------------------------------------------- |
| Dialogue segment has no speaker attribution              |  2453 | Primary cause of the high review count                   |
| Dialogue speaker was inferred with low confidence        |   731 | Attribution found a hint but stayed review-safe          |
| Alternating unattributed dialogue needs speaker review   |    97 | Two-speaker/turn-taking ambiguity remained unresolved    |
| Quoted text has an opening quote without a closing quote |    74 | PDF/OCR/segmentation quote boundary risk                 |
| Possible inferred scene break needs review               |     4 | Small number of structural boundary questions            |
| Local LLM atom grouping failed validation                |     4 | Safety fallback worked; deterministic segments were kept |
| No explicit scene breaks were found                      |     2 | Info-level scene-boundary fallback                       |

By scope:

| Scope   | Count |
| ------- | ----: |
| segment |  3355 |
| scene   |    10 |

By severity:

| Severity | Count |
| -------- | ----: |
| warning  |  3363 |
| info     |     2 |

The high warning count is therefore not primarily chapter/scene failure. It is mostly unresolved or low-confidence speaker attribution repeated at segment scope.

### Cast Discovery Issues

| Issue title                                      | Count |
| ------------------------------------------------ | ----: |
| Possible duplicate cast candidate                |   435 |
| Low-confidence cast candidate                    |   125 |
| LLM cast discovery skipped a segment window      |    98 |
| LLM speaker attribution skipped a segment window |     2 |

All `660` issue rows were `cast_discovery` warnings and remained open.

### Character and Attribution Output

Character Bible:

| Metric               | Value |
| -------------------- | ----: |
| Total characters     |   601 |
| Supporting role type |   570 |
| Narrator role type   |    31 |

Speaker attributions:

| Metric                 | Value |
| ---------------------- | ----: |
| Total attribution rows |  6995 |
| Approved rows          |  4321 |
| Needs review rows      |  2674 |
| Deterministic rows     |  6024 |
| Ollama-assisted rows   |   971 |

The approved attribution count is not equivalent to dialogue coverage. Many approved rows can be narration/default narrator rows, while the dialogue-specific coverage remained only `7.0%`.

### Product Interpretation

The job succeeded technically, but the result is not yet a production-grade review experience for this manuscript.

What worked:

- the long job completed;
- source artifacts, structure rows, cast rows, speaker attribution rows, warnings, and issues were persisted;
- LLM grouping was used when valid and rejected when invalid;
- offset validation produced zero failures;
- segment length stayed controlled on average;
- the workflow failed closed instead of hallucinating confident speaker assignments.

What did not work well enough:

- `5` chapters and `8` scenes for `6995` segments is suspicious for a full novel;
- no container-derived chapter signals were available for this PDF;
- OCR/front-matter/page-artifact contamination appears to have reached structure extraction;
- cast discovery produced `601` candidates with many noisy names/entities;
- duplicate cast candidates dominated the issue queue;
- dialogue attribution coverage was only `7.0%`;
- review warnings were counted per segment instead of grouped into manageable tasks.

### Root-Cause Hypothesis

The warning volume appears to come from four compounding causes:

1. **PDF text quality and front matter:** OCR pages, long paragraphs, catalog/front-matter text, and deterministic cleaning volume created noisy canonical input.
2. **Chapter/scene under-detection:** the parser found only 5 chapters and 8 scenes, which limits same-scene speaker context and active-speaker inference.
3. **Noisy cast graph:** cast extraction admitted many candidate strings that look like entities, fragments, or OCR/segmentation artifacts, causing duplicate and low-confidence review load.
4. **Per-segment review model:** unresolved dialogue is represented as thousands of independent warnings rather than grouped by scene, exchange, repeated pattern, or candidate speaker cluster.

### Architecture Gap Exposed by the Run

The current architecture is strong at preserving evidence and avoiding unsafe automation, but weak at **review-volume management**.

The next architecture improvement should not be simply "make the model guess more." It should add a review aggregation layer between parser diagnostics and UI review:

```text
raw warnings/issues
  -> grouping by source cause, scene, candidate, and repeated rule
  -> ranked review tasks
  -> bulk fix / propagation
  -> recompute affected warnings
```

Examples:

- collapse `2453` unresolved speaker warnings into scene-level dialogue attribution tasks;
- group duplicate cast candidates by normalized-name pair or candidate cluster;
- group quote warnings by source page/chapter and likely OCR source;
- suppress or archive warnings that become resolved after a propagated speaker assignment;
- distinguish "critical structure blockers" from "bulk cast cleanup."

### Recommended Fix Order

1. **Source cleanup gate before structure extraction**
   - Add a preflight score for OCR pages, long paragraphs, front/back matter, and page artifacts.
   - Warn the user before running a 7-hour structure job on noisy canonical text.

2. **PDF/front-matter filtering**
   - Improve removal or classification of catalog, copyright, title-page, diagram, and front/back matter blocks.
   - Prevent these blocks from producing cast candidates.

3. **Chapter and scene recovery**
   - Add PDF-specific chapter heading heuristics and tests for numeric-only/centered/roman headings.
   - Use page breaks and typography/OCR layout hints where available.

4. **Cast candidate precision**
   - Add stricter candidate filters for sentence fragments, all-caps headings, punctuation-heavy strings, and non-person entities.
   - Batch duplicate verification and apply existing merge decisions earlier.

5. **Speaker attribution depth**
   - Improve scene windows after better scene detection.
   - Let approved corrections propagate more aggressively across repeated same-name/same-pattern rows.
   - Re-run attribution after cast cleanup.

6. **Review aggregation**
   - Add a durable `review_work_items` or equivalent read model that groups thousands of raw findings.
   - UI should show "12 cast clusters" or "8 scene attribution groups," not "3363 warnings" as the primary task.

7. **Quality score thresholds**
   - Add actionable status bands:
     - green: ready for production;
     - yellow: review recommended;
     - red: source/structure quality too poor for efficient downstream production.

## Open Architecture Questions

- Should long-running structure jobs persist phase checkpoints so an API restart can resume rather than fail?
- Should PDF imports expose a mandatory Clean Text Review gate when source quality is below threshold?
- Should cast discovery be prevented from creating Character Bible rows until after front/back matter is excluded?
- Should speaker review be scene-first rather than segment-first?
- Should raw parser warnings remain visible by default, or only after expanding grouped review work?

## Source Documents

This consolidated document summarizes the current architecture from:

- [`current-pipeline-behavior.md`](current-pipeline-behavior.md)
- [`pipeline-manifest-spec.md`](pipeline-manifest-spec.md)
- [`../pipeline/ingestion/pdf-ocr-ingestion.md`](../pipeline/ingestion/pdf-ocr-ingestion.md)
- [`../pipeline/ingestion/clean-text-review.md`](../pipeline/ingestion/clean-text-review.md)
- [`../pipeline/structure/structure-parser-v2.md`](../pipeline/structure/structure-parser-v2.md)
- [`../pipeline/casting/character-bible.md`](../pipeline/casting/character-bible.md)
- [`../pipeline/casting/speaker-attribution.md`](../pipeline/casting/speaker-attribution.md)
- [`../pipeline/direction/direction-studio.md`](../pipeline/direction/direction-studio.md)
- [`../pipeline/tts/tts-production-upgrade.md`](../pipeline/tts/tts-production-upgrade.md)
- [`../pipeline/review/review-patch-workbench.md`](../pipeline/review/review-patch-workbench.md)
- [`../pipeline/qa/readiness-qa.md`](../pipeline/qa/readiness-qa.md)
- [`../pipeline/export/export-polish.md`](../pipeline/export/export-polish.md)
