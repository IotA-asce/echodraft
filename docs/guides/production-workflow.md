# Production Workflow

This guide walks through producing an audiobook draft in Echodraft, from creating
a project through exporting a chaptered audio package. It assumes Echodraft is
already installed and running; see the [getting started guide](getting-started.md)
for installation, configuration, and TTS setup. See also the
[docs index](../README.md) and the [repository root README](../../README.md).

## Workflow overview

```text
Create project
  → Import manuscript
  → Extract chapters, scenes, and segments
  → Edit individual segments
  → Configure narrator / voice settings
  → Produce chapter audio
  → Review transcript, issues, waveform markers, and patch weak lines
  → Mark listened-and-approved chapters
  → Export WAV, MP3, or M4B package
```

The core design rule is simple:

> **A segment is the smallest editable, renderable, reviewable, and patchable unit.**

That means fixing one bad line should not require regenerating the whole chapter or losing previous render history.

## 1. Create a project

In the dashboard, enter a title and optional author, confirm that you have the rights to produce the audiobook, and select **Create project**.

Echodraft rejects projects without a declared rights status.

## 2. Import a manuscript

Open the project and import a `.txt`, `.md`, `.markdown`, `.docx`, `.epub`, or `.pdf` file.

Echodraft preserves the original, applies deterministic clean-text rules, creates canonical text, and reports parser warnings. Review the preview and Clean Text Review issues before continuing.

Use **Reparse** to repeat normalization from the preserved source.

For best chapter detection, use Markdown-style headings such as:

```md
## Chapter 1
```

or

```md
# Chapter 1
```

## 3. Extract structure

Select **Extract structure**.

Echodraft splits the manuscript into:

```text
Project
  → Chapters
    → Scenes
      → Segments
```

The default maximum segment size is 600 characters. Structure Parser v3 records deterministic evidence and warnings, supports segment locks, and lets you split or merge segments before production. It preserves container chapter signals, classifies explicit front/back matter, records language evidence, keeps multi-paragraph dialogue as dialogue, routes footnote-like paragraphs for review, and uses clause-aware prosody fallback for long narration. When the default Ollama model is installed through Model Center, Extract Structure also refines bounded segment windows locally; it never sends full books or large chapters to the model. If Ollama is not ready or returns invalid segmentation, deterministic structure is kept with a warning.

## Character Bible

Use **Cast Review & Voice Bible** to maintain project cast records before production. Character records now store canonical names, aliases, traits, first-seen references, lock state, merge/split history, and optional voice links. Merge and split operations preserve traceability instead of deleting source records.

Character voice links become production inputs after Cast Review approves a segment speaker attribution.

Extract Structure now creates the first cast and speaker draft automatically: deterministic and local LLM-assisted cast extraction run when available, merge verification prevents obvious duplicates, high-confidence unique characters are created, and ambiguous candidates stay in review issues. Speaker attribution includes conservative active-speaker, interruption, vocative, pronoun, and turn-taking rules before optional bounded local LLM attribution. Approved character attributions with voice links are used during chapter production unless a segment-level voice override is set.

Voice suggestions rank existing project voices against observed character traits and Kokoro voice-ID facets. Auditions use representative character lines rather than a generic preview sentence.

## Direction Studio

Use **Infer directions** after structure extraction to seed segment delivery settings locally. Segment direction records store controlled emotion labels, pace, intensity, pauses, emphasis, whispering, lock state, evidence, and a direction fingerprint. Deterministic inference is the default; optional local LLM inference uses bounded scene windows and never overwrites user-locked directions. Manual Direction Studio saves are locked and take effect in chapter production unless an older production override already supplies a direction.

## 4. Edit segments

Select a segment to open the inline multiline editor.

The editor shows:

* next revision number;
* character count;
* validation feedback;
* save/cancel controls;
* unsaved-change protection.

Keyboard shortcuts:

* `Ctrl+Enter` or `Cmd+Enter`: save a new revision
* `Esc`: cancel the edit

Saving never overwrites history. Older segment text remains available through the segment revision API.

## 5. Configure voices

Open **Voice setup** inside the selected project.

Use one of two modes:

| Mode                 | Use it when                                                   |
| -------------------- | ------------------------------------------------------------- |
| `mock`               | You want to validate the workflow without downloading a model |
| Kokoro managed setup | You want local spoken audio from Kokoro ONNX                  |
| Piper fallback       | You have a local Piper CLI and ONNX voice model               |
| XTTS-v2 opt-in       | You have a local Coqui runtime and consented reference WAV    |

For the first run, start with mock TTS. It creates deterministic silent WAV files so you can test ingestion, rendering, assembly, patching, and export before introducing a real model.

## 6. Produce chapter audio

Select a chapter and choose **Produce chapter**.

Echodraft renders only missing or stale segments, assembles a new immutable chapter render, and exposes the result in the dashboard.

Use **Force regenerate** when you intentionally want a fresh render lineage even if the source and settings are unchanged.

## 7. Review and patch

Use **Review & patch** to:

* inspect automated QA findings;
* review the active chapter transcript with speaker colors and waveform issue markers;
* jump from a readiness or transcript issue to the relevant segment and audio moment;
* leave local comments;
* resolve issues;
* patch a specific segment;
* rebuild the affected chapter;
* mark the active chapter render as listened and approved.

The review loop is designed around fixing weak lines without destroying the rest of the chapter.

The dashboard also shows a unified next-best-action card that merges workflow state, readiness findings, export blockers, transcript markers, and chapter approval state into a ranked action with a deep link.

## 8. Export

Select one or more chapters under **Export** and create a WAV, MP3, or M4B package.

Each ZIP contains:

* active chapter renders;
* export manifest;
* checksum data.

MP3 and M4B exports require local FFmpeg. Export preflight is scoped to the selected chapter set, so unrelated chapter blockers do not prevent exporting a smaller package. M4B exports include a chapter-marked AAC audiobook file, and MP3/M4B requests can include a retail sample clip.

For installation, TTS provider setup, and troubleshooting, see the [getting started guide](getting-started.md).
