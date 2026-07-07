# Review Experience v2 — Listen-First, Task-Grouped Review

See also: [review-patch-workbench.md](review-patch-workbench.md) (the v1 workbench this
document replaces), [readiness-qa.md](../qa/readiness-qa.md) (the durable checks/issues
layer review tasks are built on), [qa-rulebook.md](../qa/qa-rulebook.md) (audio QA finding
categories/thresholds), [../../architecture/extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)
(§Confidence & flag model — the pipeline-side contract this document consumes),
[../../ui/frontend-architecture.md](../../ui/frontend-architecture.md) (the `/review/[chapterId]`
route, virtualization, TanStack Query cache model this doc's UI is built inside),
[../../ui/design-system.md](../../ui/design-system.md) (Drawer, Badge, Waveform, Diff/compare
components reused below), [../../product/product-vision-v2.md](../../product/product-vision-v2.md)
(the zero-touch principle and < 20-flags budget this document is verified against),
[../../domain/domain-model-v2.md](../../domain/domain-model-v2.md) and
[../../api/api-v2-contracts.md](../../api/api-v2-contracts.md) (data model / endpoint contracts
for the `review_tasks` layer specified at a UX level here).

## Purpose

Today, "review" means opening a queue of 3,000+ per-segment warnings and working through it
like a punch list. [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)
makes that queue nearly empty by construction — most decisions are auto-accepted with an
audit trail, and what remains is grouped into a handful of durable review tasks (target:
**< 20 per book**). This document specifies what review *feels like* once that pipeline
change lands: not a worklist to clear, but an audiobook to listen to, with fixing built
into the act of listening rather than gating it.

The reframe in one sentence: **review changes from "resolve 3,000 warnings" to "listen and
spot-fix."**

## Goals

1. **Review is optional by design.** A book that finishes the pipeline with zero flags is
   a complete, exportable audiobook with no review step required — not a draft waiting on
   a queue. The UI must never present review as a gate between "pipeline done" and "book
   done."
2. **When a user does review, the workflow is listen-first, not list-first.** The primary
   review surface is the audiobook player with a synchronized transcript, not a table of
   findings. Findings surface *as markers on what you're already listening to*, not as a
   separate screen you triage before you're allowed to listen.
3. **Total required review time for a typical book is zero.** No book requires a human
   listen-through, a queue clear, or an approval click to be exportable. "Required" review
   time is a hard `0`, matched to [product-vision-v2.md](../../product/product-vision-v2.md)
   §2.2 rule 1 (a run completes with zero required human input).
4. **Typical *chosen* review time is ≤ 1 hour for a full book.** For a user who does choose
   to review (an indie author checking their own book, a producer spot-checking before
   distribution), the grouped-task model plus skim mode should make a full pass — listening
   to every flagged moment and skimming the rest — take under an hour for a 500-page/~8-hour
   audiobook. This is the number [Metrics](#metrics) below is measured against.
5. **Fixing a problem is as fast as noticing it.** The spot-fix loop (hear → tap → fix →
   re-render → resume) has a latency budget so a fix never breaks listening flow (see
   [Listen-first review flow](#listen-first-review-flow)).
6. **Every automated decision stays inspectable, evidence-backed, and reversible**, even
   the ones that never became a flag — this is the same principle
   [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) states for
   auto-accepted pipeline output, carried through to the UI as the evidence/lineage surface
   in [Comparison & lineage UX](#comparison--lineage-ux).
7. **Preserve every hard architectural constraint**: segment-first editing, manifest-driven
   state, patchable/targeted re-render, append-only render history, no audio blobs in the
   relational DB.

## Non-goals

- This document does not change *what* gets flagged or *how confident* the pipeline is —
  that is entirely [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)'s
  contract (the three-tier auto-accept/audit/flag policy and the task-grouping rules). This
  document specifies the UX that consumes that contract.
- This document does not redesign TTS synthesis, emotion rendering, or voice matching — those
  are [tts-engine-strategy.md](../tts/tts-engine-strategy.md) and
  [automatic-casting-v2.md](../casting/automatic-casting-v2.md). Spot-fix actions call into
  those systems; they don't reimplement them.
- This document does not specify the job orchestrator, DAG, or event push mechanics used to
  prioritize a spot-fix render over background work — that is
  [target-architecture.md](../../architecture/target-architecture.md); this document specifies
  the *contract* review needs from it (a priority flag on render requests).
- This document does not redesign export/rights/mastering — [export](../export/) docs own that;
  §5 here only touches the approval *badge* that export reads.
- No collaboration/multi-reviewer workflow (assignment, comments-as-discussion-threads across
  users) — out of MVP scope per [product-vision-v2.md](../../product/product-vision-v2.md) §4/§7.

## Current-state analysis: why the v1 model overwhelms users

### The warning flood

The real measured reference run (`job_3c8fbf0189cd4c8e`, 6,995 segments) produced:

| Source | Count |
|---|---|
| `structure_parser_warnings`: "Dialogue segment has no speaker attribution" | 2,453 |
| `structure_parser_warnings`: "low confidence speaker" | 731 |
| `structure_parser_warnings`: unbalanced quotes | 74 |
| Cast-discovery candidates | 601 |
| — of which flagged as possible duplicates | 435 |

That is **3,258 per-segment warnings plus 435 cast-duplicate issues on one book** — roughly
one warning for every two segments. None of these are aggregated: each is a standalone row
in a list, with no notion that 700 "low confidence speaker" rows in the same three-way
alternating conversation are *one* underlying ambiguity, not 700 independent ones. A reviewer
facing this queue cannot tell which 20 rows actually matter; the queue itself is the UX
failure, independent of whether any individual finding is correct.

### The 6-pane inspector

[review-patch-workbench.md](review-patch-workbench.md) (Stage 12, v1) answers the flood by
building a deeper inspector, not a smaller queue: opening `Inspect` on a single segment loads
source text, canonical text, parser evidence, cast/attribution, direction, render history,
waveform metadata, QA findings, comments, and patch attempts — a **six-plus-pane layered
read model per segment** (`SegmentReviewInspector`). This is the right *depth* of information
for the rare segment that genuinely needs it, but it is presented as the default unit of
review work, one segment at a time, with no notion of "this segment is fine, skip it" faster
than opening and closing the inspector. At 6,995 segments, "inspect one at a time" does not
scale even before the flood of warnings is considered — this is the same root cause
[frontend-architecture.md](../../ui/frontend-architecture.md) documents for the wider UI (no
virtualization, one heavyweight `SegmentEditorCard`/inspector load per row).

### The issue/warning duality

v1 review data is split across two barely-reconciled tracks:

- **`structure_parser_warnings`** — per-scope findings from the structure/attribution passes,
  ungrouped, with no resolution workflow beyond "combine with open cast issues in the Parser
  Review queue" ([review-patch-workbench.md](review-patch-workbench.md)).
- **`issues`** — durable, resolvable rows (categories: cast_discovery, render QA
  [missing_audio/clipping/excessive_silence/truncation/asr_word_mismatch], export blockers;
  severities info/warning/blocking/error; deduplicated by `dedupe_key`; `resolved`/`ignored`/
  `locked` states per [readiness-qa.md](../qa/readiness-qa.md)).

A reviewer has to learn both models to know where a given problem lives, whether it has a
resolution action, and whether resolving it is durable (an `issue`) or cosmetic (a `warning`
with no persisted state). The dashboard's "Parser Review" queue papers over this by combining
both into one list, but the underlying duality remains: two data shapes, two different
resolution semantics, one UI trying to make them look like one thing.

### Why the model overwhelms users — the actual mechanism

Putting the three problems together: **the number of findings is unmanageable (thousands),
the unit of review is too fine-grained (one segment, six panes, one at a time), and the data
model actively resists grouping (two disjoint shapes with no native "these five things are
one problem" relationship).** A reviewer cannot triage by importance because nothing is
ranked across the flood; cannot batch-resolve because nothing is grouped; and cannot trust
"done" because `warnings` have no terminal state to reach. The result, observed directly: the
UI melts trying to render thousands of rows
([frontend-architecture.md](../../ui/frontend-architecture.md) root-cause analysis), and even
if it didn't, no human would work through 3,258 rows one at a time. The fix is not a faster
list — it is making the list nearly disappear (extraction-pipeline-v2's job) and replacing
"work the list" with "listen to the book" as the default interaction (this document's job).

## The grouped review-task model

### Consuming the pipeline's contract

[extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) §Confidence & flag
model defines the producer side: a three-tier policy (auto-accept / auto-accept-with-audit-
trail / flag) applied per stage, and an aggregation rule that groups flags "by cause" into a
budget of **< 20 grouped review tasks per book**, each carrying "the evidence for every
member so a reviewer resolves a cluster of related decisions in one action." This section
specifies the UX-facing shape of that grouping: what a task looks like, how it's ordered, how
a user resolves it, and how it moves through its lifecycle.

**Design rule carried through from the pipeline contract:** a review task is never invented
by the UI from raw per-segment data. It is always the render of a `review_tasks` row that the
pipeline (or readiness QA) created by grouping one or more durable `issues`/readiness-check
rows under one dedupe key. The UI does not do its own ad-hoc grouping of a flat issue list —
that would silently reintroduce a second source of truth for "what needs review." See
[Data model/API impact](#data-modelapi-impact) for the exact relationship between
`review_tasks` and the existing `issues` table.

### Task types

Every task belongs to exactly one type, each with its own icon, evidence shape, and default
resolution actions. This is the exhaustive v1-launch list; new types are additive, never a
schema break.

| Type | Example title | Source stage | Typical member count |
|---|---|---|---|
| `cast_merge` | "3 possible character merges to confirm" | S3 cast reconcile (residual cluster ambiguity) | 1 pair per member |
| `cast_name` | "2 characters need a name confirmation" | S3 profile synthesis (low-confidence display name) | 1 character per member |
| `attribution_ambiguous` | "4 scenes have ambiguous speakers — listen to 12 lines" | S4 attribution reduce (vote disagreement / alternation break) | ~3 segments per scene member |
| `structure_span` | "1 structural span in Chapter 3 could not be segmented cleanly" | S2 structure repair-loop exhaustion | 1 span per member |
| `direction_outlier` | "1 chapter has a delivery outlier worth a listen" | S5 direction inference (emotion/intensity far outside the character's baseline with low confidence) | 1–3 segments per member |
| `audio_qa` | "2 chapters have audio QA findings" | Render QA (clipping / excessive_silence / dead_air / truncation_suspected / loudness — see [qa-rulebook.md](../qa/qa-rulebook.md)) | 1 segment or chapter per member |
| `pronunciation_gap` | "1 name is pronounced inconsistently across chapters" | Cross-chapter TTS consistency check | 1 term per member |

Every type maps to exactly one v1 source so migration is traceable (see
[Migration: v1 issues/warnings → tasks](#migration-v1-issuesconfirmingsattribution-mapping)).

### Task anatomy

```json
{
  "id": "task_9f2c…",
  "type": "attribution_ambiguous",
  "title": "4 scenes have ambiguous speakers",
  "summary": "12 lines across chapters 6, 9, 14, 22 where the model's self-consistency vote did not converge above the confidence threshold.",
  "priorityTier": "audible",
  "priorityScore": 742.5,
  "status": "open",
  "scope": {
    "chapterIds": ["chp_06", "chp_09", "chp_14", "chp_22"],
    "sceneIds": ["scn_…"],
    "segmentIds": ["seg_…", "seg_…"]
  },
  "members": [
    {
      "segmentId": "seg_04821",
      "chapterId": "chp_06",
      "sceneId": "scn_0142",
      "excerpt": "\"You already knew, didn't you.\"",
      "evidence": {
        "candidates": [
          {"characterId": "chr_reyes", "displayName": "Reyes", "voteShare": 0.6},
          {"characterId": "chr_okonkwo", "displayName": "Okonkwo", "voteShare": 0.4}
        ],
        "confidence": 0.58,
        "method": "vote",
        "llmRunIds": ["run_a1…", "run_a2…", "run_a3…"]
      },
      "resolutionActions": [
        {"action": "confirm_speaker", "characterId": "chr_reyes"},
        {"action": "confirm_speaker", "characterId": "chr_okonkwo"},
        {"action": "listen_in_context", "startMs": 812340}
      ]
    }
  ],
  "bulkActions": [
    {"action": "accept_top_vote_all", "label": "Accept the top vote for all 12 lines"},
    {"action": "mark_reviewed_all", "label": "Mark all 4 scenes reviewed without changes"}
  ],
  "sourceIssueIds": ["iss_…", "iss_…", "iss_…"],
  "createdFromRun": {"stage": "attribution-v2", "manifestVersion": "attribution-v2", "runId": "run_…"},
  "createdAt": "2026-07-05T10:14:02Z",
  "resolvedAt": null,
  "verifiedAt": null
}
```

Fields that matter for the UX contract:

- **`scope`** is always resolvable to playable audio — chapter/scene/segment IDs the player
  can jump to, never a bare description. A task the UI cannot deep-link into audio is a
  modeling bug, not an acceptable state.
- **`members[].evidence`** carries exactly what
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) already produces
  per decision (candidates, confidence, method, `llmRunId`s) — the UI never re-derives
  evidence, it renders what the manifest already recorded.
- **`resolutionActions`** are one-tap: each is a fully-specified API call (an action name plus
  the parameters needed to execute it), never a form the user fills in from scratch. A
  reassignment action already knows the top-3 candidate character IDs; the user picks one.
- **`bulkActions`** exist on every task with more than one member, so a task never *requires*
  member-by-member resolution — "accept the model's top vote for all 12 lines" is a single
  tap that resolves the whole task when the reviewer trusts the aggregate.
- **`sourceIssueIds`** is the pointer back to the durable `issues`/readiness-check rows this
  task groups — see [Data model/API impact](#data-modelapi-impact).

### Priority ordering algorithm

Tasks are shown in one ranked list (never re-sortable into a flood by the user re-adding
per-column sort — one ranking, computed server-side, matching
[design-system.md](../../ui/design-system.md) §8 rule 1's "one primary action" discipline
applied to lists: one primary *order*, not a spreadsheet).

**Tier first, score within tier.** Three priority tiers, checked in this order:

| Tier | Definition | Examples |
|---|---|---|
| `blocking` | The task contains at least one member that gates export today (an unresolved `blocking`/`error` severity issue) | `structure_span` repair failure, `audio_qa` with `missing_audio` |
| `audible` | The task represents something a listener would actually notice if unresolved (wrong speaker voice, a flat delivery outlier, clipping/dead-air) but does not block export | `attribution_ambiguous`, `direction_outlier`, most `audio_qa` |
| `cosmetic` | The task is unlikely to be perceptible in normal listening (a display-name spelling ambiguity, a duplicate-candidate merge with near-identical voices) | `cast_name`, low-impact `cast_merge` |

Within a tier, tasks are ordered by a **prominence-weighted score**:

```
score(task) = tierBase(task.priorityTier)
            × log(1 + memberCount(task))
            × prominenceWeight(task.scope)
            × (1 - confidenceGapPenalty(task))

tierBase:            blocking=1000, audible=100, cosmetic=10
memberCount:         number of affected segments/candidates in the task
prominenceWeight:    max over affected chapters of:
                        1.5  if chapter is the earliest unlistened chapter
                        1.2  if chapter falls in the first quarter of the book
                              (a wrong voice in chapter 1 is heard by everyone
                              who ever starts the book; one in chapter 40 is not)
                        1.0  otherwise
                        0.6  if the chapter's audio has already been
                              marked "listened and approved" (§Chapter/book
                              approval model v2) — surfaced but deprioritized,
                              since a human already vetted this audio
confidenceGapPenalty: 0.3 if the pipeline's own confidence for the flagged
                        decision is just below the flag threshold (MID − ε);
                        0.0 if confidence is far below threshold (genuinely
                        ambiguous, not a borderline call) — a near-miss on
                        the threshold is lower-value to review than a
                        decision the model was actually unsure about
```

`log(1 + memberCount)` rather than raw `memberCount` deliberately keeps a 12-line
`attribution_ambiguous` task from crowding out a 1-member `structure_span` task in the same
tier — task *count* should stay legible even when member count varies widely; a huge task is
worth somewhat more attention than a tiny one, not twelve times more.

The ranked list is what the Overview screen's `NeedsAttentionList`
([frontend-architecture.md](../../ui/frontend-architecture.md)) and the review screen's task
rail both render — one order, computed once server-side per
`GET /api/v1/projects/{projectId}/review-tasks` (see
[Data model/API impact](#data-modelapi-impact)), not re-derived per screen.

### Task lifecycle

```
        pipeline groups issues under a dedupe key
                        │
                        ▼
                    ┌────────┐
        ┌──────────▶│  OPEN  │◀─────────────────────┐
        │           └───┬────┘                      │
        │               │                            │ reopen: a
        │   user taps a │   pipeline re-run/patch    │ "resolved" or
        │   resolution  │   makes every member's      │ "auto_resolved" task's
        │   action, or  │   underlying check pass     │ member check fails
        │   a bulk      │   (auto-resolve, same       │ again on the next
        │   action      │   pattern as readiness's    │ readiness run
        │               │   auto-resolve-on-pass)     │
        │               │                            │
        ▼               ▼                            │
   ┌──────────┐   ┌──────────────────┐               │
   │ RESOLVED │   │ AUTO_RESOLVED_BY_ │               │
   │          │   │ RERUN             │               │
   └────┬─────┘   └────────┬──────────┘               │
        │                  │                          │
        │   next readiness run / patch QA re-verifies │
        │   every member's underlying check           │
        └────────────────┬─────────────────────────────┘
                          ▼
                    ┌──────────┐
                    │ VERIFIED │  (terminal — re-verified check still
                    └──────────┘   passes; task drops off the active list)
```

State semantics, matching the re-verification discipline
[readiness-qa.md](../qa/readiness-qa.md) already establishes for issues (never trust a stale
status string; re-derive from live checks):

- **`open`** — at least one member's underlying check has not passed and no resolution action
  has been applied yet.
- **`resolved`** — a human applied a resolution action (a one-tap fix, a bulk action, or an
  explicit "mark reviewed, no changes") to every member. This is a *claim*, exactly like
  `readiness-qa.md`'s issue `resolved` status — it stands until the next check run.
- **`auto_resolved_by_rerun`** — no human action was needed; a later pipeline stage re-run or
  an upstream patch (e.g. a cast merge that re-points attribution) made every member's
  underlying check pass on its own. Recorded distinctly from `resolved` so
  [Metrics](#metrics) can separate human effort from pipeline self-correction.
- **`verified`** — terminal state: the next readiness run (or the patch-triggered re-check for
  render-QA-sourced tasks) re-evaluated every member's underlying check and confirmed it still
  passes. A `resolved`/`auto_resolved_by_rerun` task moves to `verified` automatically; it
  never requires a second human action.
- **Reopen** — if re-verification finds a member's check failing again (e.g. a `resolved`
  `cast_merge` gets contradicted by a later chapter's evidence during book-level
  reconciliation), the task returns to `open` with `"reopened": true` in its metadata,
  mirroring the existing issue-reopen behavior in `readiness-qa.md`.

A task is never silently deleted. `verified` tasks remain queryable (filtered out of the
active list by default) so the full history of what was ever flagged and how it was resolved
stays inspectable — the same append-only spirit as render history, applied to the review
ledger.

### Migration: v1 issues/warnings → tasks

| v1 source | v1 shape | v2 task type | Grouping key |
|---|---|---|---|
| `structure_parser_warnings`: "no speaker attribution" | per-segment warning, ungrouped | `attribution_ambiguous` | scene ID (post S4-v2, these mostly stop being generated at all — see below) |
| `structure_parser_warnings`: "low confidence speaker" | per-segment warning, ungrouped | `attribution_ambiguous` | scene ID |
| `structure_parser_warnings`: unbalanced quotes | per-segment warning, ungrouped | `structure_span` | chapter ID / span |
| `issues` category `cast_discovery` (duplicate suspects) | per-candidate issue | `cast_merge` | cluster ID (S3-v2's clustering, not per-pair) |
| `issues` category `cast_discovery` (low-confidence create) | per-candidate issue | `cast_name` | character ID |
| `issues` render QA (`missing_audio`/`clipping`/`excessive_silence`/`truncation`/`asr_word_mismatch`) | per-segment/chapter issue | `audio_qa` | chapter ID |
| *(new in v2 — no v1 equivalent)* | — | `direction_outlier` | scene ID |
| *(new in v2 — no v1 equivalent)* | — | `pronunciation_gap` | pronunciation term |

**Volume reality check.** This mapping is not "repackage the same 3,258 rows into fewer
containers" — the overwhelming majority of what generated `structure_parser_warnings` in v1
never reaches the flag stage in v2 at all, because S4-v2 makes the LLM the primary attributor
with voting and book-level reconciliation instead of flagging every rule-cascade miss (see
[extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) §S4). What used to
be 2,453 + 731 individual warnings becomes, per the pipeline's own budget, a handful of
`attribution_ambiguous` tasks (genuinely-unresolved-after-voting scenes only) — typically
low single digits on a well-behaved book, not "2,453 grouped into 4 buckets." The `< 20
tasks/book` target in [product-vision-v2.md](../../product/product-vision-v2.md) is a sum
across *all* task types, not a per-type allowance.

**No dangling v1 UI.** The Parser Review queue, the Structure & Cast Draft warning list, and
the six-plus-pane always-open inspector all retire; see
[Migration path from review-patch-workbench](#migration-path-from-review-patch-workbench) for
exactly which pieces survive as the inspector drawer.

## Listen-first review flow

### The review surface is the player

The primary (and, for most books, only) review surface is the chapter audio player with a
synchronized transcript — the `/projects/[projectId]/review/[chapterId]` route in
[frontend-architecture.md](../../ui/frontend-architecture.md). There is no separate "resolve
findings" mode a user has to switch into before they're allowed to press play: continuous
playback is the default and only starting state. Review tasks surface as markers on the
waveform and highlighted rows in the transcript that the user encounters *while listening*,
not as a gate in front of the play button.

Concretely, opening a chapter for review does three things at once, none of which blocks the
others:

1. Starts (or resumes) continuous playback of the chapter's current active render.
2. Renders `WaveformCanvas` with issue markers for every task member in this chapter
   ([design-system.md](../../ui/design-system.md) §6 Waveform display; marker styling in
   [Waveform/transcript issue markers](#waveformtranscript-issue-markers) below).
3. Scrolls `TranscriptListVirtual` to the playhead, keeping it in sync as playback continues.

A user who presses play and does nothing else has performed a complete, valid review session
— they listened, heard nothing wrong, and can close the tab. Nothing in the UI asks them to
"finish reviewing" first.

### The spot-fix loop

The core interaction. Every fix follows the same shape regardless of what's wrong:

```
 1. HEAR       user notices something wrong while listening (a marker may or
               may not be present — the ear is still the primary detector;
               markers are an aid, not a requirement)
        │
 2. TAP        user taps the transcript line (or the waveform marker, or
               pauses and taps the nearest line) → Inspector drawer opens,
               scoped to that segment, playback pauses at the tap point
        │
 3. FIX        contextual fix actions appear based on the segment's evidence
               and any open task membership (see action table below)
        │
 4. RE-RENDER  the fix action issues a targeted segment patch
               (POST …/segments/{segmentId}/patch, force=true — existing
               patchability contract, unchanged) tagged priority=spot_fix
        │
 5. RESUME     playback resumes automatically at the fixed segment's start
               once the new render is ready and the chapter is reassembled
```

**Contextual fix actions per problem type:**

| Problem | Action | Mechanism |
|---|---|---|
| Wrong speaker | Reassign from top-3 candidates, each with an instant voice preview (a short cached audition clip of that character's assigned voice reading a stock phrase — not a full segment re-render) before committing | `PATCH` the segment's speaker attribution (existing sibling-propagation behavior preserved), then patch-render with the newly resolved voice |
| Flat/wrong delivery | Adjust emotion/intensity via the `Slider` component ([design-system.md](../../ui/design-system.md) §6), with a **re-render preview** — a debounced (~600ms after the last drag) low-latency render of just that segment plays automatically so the user hears the change before committing | `PATCH` the segment's `DirectionProfile` override, patch-render |
| Mispronunciation | Add or edit a pronunciation entry inline (reuses the existing pronunciations feature) | `POST`/`PATCH` pronunciation entry, patch-render every segment containing the term *in this chapter only* by default, with an option to apply book-wide |
| Text error | Edit the segment text inline (`TextArea`, same row-owned local-state pattern as [frontend-architecture.md](../../ui/frontend-architecture.md)'s `SegmentRow`) | `PATCH` segment text (creates a new revision, existing behavior), patch-render |
| Genuinely fine, task member was a false flag | "Mark reviewed, no change" | Resolves the task member without mutating the segment |

Every action above is also individually reachable from the task list (a review task's
`resolutionActions`), so the loop works identically whether the user arrived via listening or
via the ranked task list — one interaction model, two entry points.

**Latency budget: fix-to-audible < 15 seconds.** This is what keeps the loop from breaking
listening flow. Budget breakdown for the dominant case (a single-segment reassignment or
direction tweak on mid-tier hardware):

| Step | Budget | Why |
|---|---|---|
| Patch request round-trip | < 200ms | Local API, no network latency to speak of |
| Segment TTS render (one short line, warm model) | < 5s | A single segment is seconds of audio; the resident TTS worker ([tts-engine-strategy.md](../tts/tts-engine-strategy.md)) is already warm |
| Segment QA (loudness/clipping/dead-air/truncation check) | < 1s | Existing `analyze_wav` numpy path, no ffmpeg round-trip needed for the segment-level check |
| Chapter reassembly (patch-scoped) | < 5s | Reassembly must only re-stitch the affected region plus enough surrounding context to re-crossfade correctly — **not** the whole chapter's ambience/mastering pass; see the render-queue note below |
| Mastering re-pass (if chapter-level loudness could shift) | best-effort, does not block resume | Playback resumes on the reassembled-but-not-yet-remastered audio; a background remaster job silently swaps in the fully mastered chapter render when ready (append-only, no perceptible gap for the user since the un-remastered reassembly is already within tolerance in the overwhelming majority of single-segment patches) |
| **Total, blocking playback resume** | **< 15s** | Sum of the first four rows on typical hardware |

**Render-queue prioritization.** The job orchestrator
([target-architecture.md](../../architecture/target-architecture.md)) accepts a `priority`
field on render requests: `spot_fix` (interactive, user is waiting) vs. `background` (bulk
chapter production, provisional re-renders from S3 book-level reconciliation, etc.). A
`spot_fix` render preempts the worker pool ahead of any queued `background` work — it does not
wait behind a book's worth of queued chapter renders. This is a thin, additive contract on top
of the existing render pipeline: the request shape gains one field
(`GenerateSegmentRequest.priority`), and the queue is a priority queue instead of FIFO for that
one field. See [Data model/API impact](#data-modelapi-impact).

If the 15s budget is exceeded (e.g. a cold TTS worker, a large XTTS voice-cloning render), the
UI does not silently stall: a compact "rendering… (Nx real-time)" indicator using the
[design-system.md](../../ui/design-system.md) determinate progress bar replaces the paused
playhead, and playback resumes the instant the render lands — never a modal, never a blocked
screen.

### Skim mode: the auto-generated review playlist

For a user who wants a faster full-book pass than listening straight through, skim mode
builds a short, stitched playlist of the **N lowest-confidence moments across attribution,
direction, and audio QA** — the same population that feeds review tasks, reordered for rapid
sequential listening rather than grouped by cause.

**Selection algorithm:**

```
candidates = all segments where:
    - it is a member of an open review task, OR
    - it was auto-accepted at the MID tier (audit-trail tier, not silently
      auto-accepted at HIGH) for attribution, direction, or QA

score(segment) = 1 - confidence(segment)      # lower confidence, higher priority
                 × prominenceWeight(segment)   # reuse the task priority-ordering
                                                # prominence weight, §priority
                                                # ordering algorithm above

playlist = top N candidates by score, deduplicated so adjacent low-confidence
           segments in the same scene collapse into one clip
           (a clip = the flagged segment ± 2 context segments before/after,
           so the moment is heard in context, not as an isolated fragment)

order = playlist sorted by (chapterIndex, segmentOrderIndex)   # book order,
                                                                # not score order —
                                                                # skimming in book
                                                                # order keeps
                                                                # continuity legible
```

`N` defaults to 20 (matching the book-level `< 20 tasks` budget — skim mode is designed to
have at most one moment per task on a well-behaved book) and is user-adjustable. Clips are
stitched with a short (200ms) silence gap — no crossfade, since each clip is a discontinuous
jump in the book and pretending otherwise would be misleading, unlike the continuous in-scene
crossfades assembly uses ([current-pipeline-behavior.md](../../architecture/current-pipeline-behavior.md)).

**Interaction:** each clip plays automatically in sequence; a persistent one-tap "Accept" /
"Fix" pair sits below the transport (`Accept` resolves the task member as "reviewed, no
change" and auto-advances; `Fix` opens the same Inspector drawer and spot-fix loop as the main
player, then auto-advances on resume). A skim-mode pass through a well-behaved book (≤ 20
clips × ~15s each) takes on the order of 5 minutes — the fast path that makes the ≤ 1 hour
typical-*chosen*-review budget achievable even for a book with every task type represented.

### Waveform/transcript issue markers

Reuses [design-system.md](../../ui/design-system.md) §2/§6 exactly — no new visual language is
introduced. Markers are monochrome, distinguished by shape and fill only:

| Task priority tier | Waveform marker | Transcript row treatment |
|---|---|---|
| `blocking` | Solid filled triangle, `--color-text-primary` | Row background `--color-surface-sunken`, leading filled-triangle glyph (Badge "Outline, red" variant is reserved for the badge/toast context per design-system §7 — the waveform/transcript marker itself stays monochrome even for blocking items, consistent with "the waveform never uses the red") |
| `audible` | Hollow/outline triangle, `--color-border-strong` stroke | Leading hollow-triangle glyph, no background change |
| `cosmetic` | Small filled dot, `--color-text-tertiary` | Leading dot glyph, `text-tertiary` label color |
| *(auto-accepted, MID tier, no open task)* | No waveform marker by default; visible only when skim mode or an explicit "show audit trail" toggle is on | No row treatment by default |

Hovering or focusing a marker opens a `Tooltip` with a one-line evidence summary (per
design-system §6 Waveform display); tapping/clicking seeks the transport and opens the
Inspector drawer scoped to that segment — identical entry point to the spot-fix loop's step 2,
whether the user arrived by ear or by marker.

## Chapter/book approval model v2

### What approval means when nothing is required

v1's "Mark listened and approved" ([review-patch-workbench.md](review-patch-workbench.md))
already treats approval as separate from automated checks ("Review complete is separate from
automated checks"). v2 keeps that separation and sharpens its meaning now that automated
checks rarely block anything:

**Approval = a "verified by human" badge, and nothing else.** It does not gate export
(zero-touch rule 1: a book with zero human approvals must still be exportable). It does not
change readiness status beyond the existing informational check. Its *only* functional effect
is on the export manifest: an exported audiobook records, per chapter, whether that chapter's
active render was ever explicitly approved by a human listen-through, and by whom/when. This
is provenance metadata for anyone who cares (an indie author distributing under their name, a
producer with a QA sign-off requirement) — not a pipeline gate.

```json
{
  "chapterId": "chp_06",
  "approvalSource": "human",
  "approvedRenderId": "chr_06_render_0042",
  "approvedAt": "2026-07-06T21:03:11Z",
  "stale": false
}
```

`approvalSource` is one of `human` (an explicit "Mark listened and approved" action on this
exact render), `auto` (see policy below), or `none`. `stale: true` when a newer chapter render
exists than the one that was approved — carried forward unchanged from v1's staleness rule.

### Auto-approval policy (optional)

For users who want the badge to reflect "the pipeline finished with no open concerns" rather
than requiring a literal human listen, a project-level setting
(`ProjectProductionSettings.autoApprovalPolicy`, default **off**) can mark a chapter
`approvalSource: "auto"` the moment its active render has zero open review tasks and passes
readiness. This is opt-in and clearly distinguished in the manifest and UI from `human` — an
`auto` badge never claims a human listened, and any UI surface showing approval status (the
Overview's `ListenFirstCard`, the export manifest) renders `auto` and `human` with visibly
different iconography (Badge "Filled solid" with a check glyph for `human`; Badge "Outline"
neutral for `auto`), so the distinction survives even a casual glance.

### Readiness recomputation

Review tasks and the approval badge both plug into the existing re-derivation discipline in
[readiness-qa.md](../qa/readiness-qa.md) rather than inventing a parallel one:

- A readiness run re-evaluates every underlying check live (never trusts a stored task/issue
  status) and, per the existing auto-resolve-on-pass rule, moves any task whose members now
  all pass into `verified` (§Task lifecycle) — this *is* the readiness auto-resolve mechanism,
  extended to also close out the grouping task, not a separate computation.
- The chapter-approval readiness check remains a `warning`, never a blocker (unchanged from
  v1) — "no automated issues" stays distinct from "a human listened and approved this exact
  active render," and neither is required for export.
- Re-rendering a chapter after approval reopens its approval staleness exactly as today
  (`stale: true`), and — new in v2 — also re-runs the auto-approval policy check if enabled, so
  an `auto`-approved chapter that changes still gets re-evaluated rather than keeping a stale
  auto-approval.

## Comparison & lineage UX

### Before/after render compare

Every patch is comparable against what it replaced using the **existing** compare endpoint —
`GET /api/v1/projects/{projectId}/segments/{segmentId}/renders/compare`
(`SegmentRenderComparison`: `currentRender`, `previousRender`, `changedFields`) — surfaced
through the [design-system.md](../../ui/design-system.md) §6 "Diff / compare view" component:
two linked-cursor compact waveforms side by side, a delta strip showing *where* the renders
differ (opacity-proportional, monochrome, never a color heatmap), and a compact key-value
metadata diff (LUFS, true peak, duration, voice, direction parameters) with changed rows
bolded and shown as `before → after` pairs. This is reused verbatim from the design system
spec — this document does not invent a new compare visualization, it wires the existing
Inspector drawer to open this view whenever a segment has more than one render in its history.

For a chapter-level patch (a fix that also changed reassembly), the same pattern applies one
level up: two chapter-scoped compact players with linked scrub, using the chapter's
`review-timeline` windowed endpoint for both the pre- and post-patch active render.

### Evidence inspection: the audit trail

"Why this speaker/voice/emotion" is answered from data the pipeline already writes, never
re-derived by the frontend:

- **Speaker**: the `attribution_manifest.json` row for the segment — `method`
  (`llm`/`det_shortcircuit`/`vote`/`reduce_repair`/`propagated`), `confidence`, the candidate
  set considered, and (for votes) the sample tally, per
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) §S4.
- **Voice**: the casting decision's evidence from
  [automatic-casting-v2.md](../casting/automatic-casting-v2.md) — which catalog voice was
  matched, the character-profile facets that drove it, and the distinctiveness check against
  sibling characters.
- **Emotion/delivery**: the `direction_manifest.json` row — the character's baseline speech
  style from S3, the inferred deviation, and the `llmRunId` that produced it.

All three render inside the Inspector drawer's evidence disclosure — collapsed by default,
`--font-mono` for raw IDs/hashes, opened only on request — exactly the pattern
[design-system.md](../../ui/design-system.md) specifies for the Diff/compare view's raw
evidence ("lives behind a collapsed Inspector disclosure at the bottom... only opened on
request"). Auto-accepted decisions (never flagged, never a task) are inspectable through this
same drawer — evidence-backed-but-not-queued (goal 6) means the drawer works identically
whether the segment was ever flagged or not; there is no separate "audit view" only for flagged
items.

### Undo model

Append-only render history (hard constraint) means every prior render is, by construction,
still on disk and still referenced by a `SegmentRenderRecord`/`ChapterRenderRecord` row. The
UI contract for "revert":

- **Revert is itself a new render, never a deletion or an un-delete.** Selecting "Revert to
  this render" on a prior entry in the render-history list creates a **new**
  `SegmentRenderRecord` whose audio artifact is the same file the reverted-to record already
  points at (no re-synthesis needed — reuse the existing artifact path) and whose metadata
  carries `revertOf: "<the render id being restored>"`. The chain (`parent_render_id`) still
  points at the most recent render before the revert, so the full lineage — including the fact
  that a revert happened — remains readable from history. This mirrors how a patch already
  works (new record, parent pointer, append-only); revert is a patch whose "fix" is "go back."
- **A reverted render is immediately playable and immediately the active render** — reassembly
  and QA re-run exactly as they do for any new render (same latency budget as
  [the spot-fix loop](#the-spot-fix-loop)).
- **Any review task or issue tied to the reverted-away render is re-evaluated, not silently
  cleared.** If the revert re-introduces the original problem, the relevant task reopens
  (§Task lifecycle's reopen path) rather than staying `resolved` on stale grounds.
- **The render-history list itself never shrinks.** Every render — including ones that were
  later reverted away from — stays visible in the Inspector drawer's render-history tab,
  consistent with "every prior render recoverable" being an always-true property of the system,
  not a feature that has to be separately preserved by the revert action.

## Data model/API impact

Full schema ownership lives in [domain-model-v2.md](../../domain/domain-model-v2.md) (tables)
and [api-v2-contracts.md](../../api/api-v2-contracts.md) (endpoints); this section states the
shape review needs from both, coordinated in parallel with those documents.

### `review_tasks` table

A grouping layer over the existing `issues`/`readiness_reports` tables — **not** a duplicate
source of truth. A task never carries its own independent pass/fail state; it is computed by
grouping existing durable rows under a stable dedupe key and re-derived the same way readiness
checks are (live re-evaluation, never a trusted cache).

```
review_tasks
  id                  text primary key
  project_id          text not null
  type                text not null            -- cast_merge | cast_name | attribution_ambiguous
                                                -- | structure_span | direction_outlier | audio_qa
                                                -- | pronunciation_gap
  dedupe_key          text not null            -- stable across reruns, same convention as issues.dedupe_key
  title               text not null
  summary             text not null
  priority_tier       text not null            -- blocking | audible | cosmetic
  priority_score      real not null            -- computed, re-derived on every read, not stored authoritative
  status              text not null            -- open | resolved | auto_resolved_by_rerun | verified
  scope_json          jsonb not null           -- chapterIds / sceneIds / segmentIds
  members_json        jsonb not null           -- per-member evidence + resolutionActions (denormalized
                                                -- from the source issues/checks for fast list rendering)
  source_issue_ids    jsonb not null           -- array of issues.id / readiness_checks.id this task groups
  created_from_run    jsonb not null           -- {stage, manifestVersion, runId}
  created_at          timestamp not null
  resolved_at         timestamp
  verified_at         timestamp
  reopened            boolean not null default false
  unique (project_id, dedupe_key)
```

No audio blobs, no waveform data — same constraint as every other table in the system;
`scope_json`/`members_json` carry IDs and small evidence snippets only, resolved into playable
artifacts through the existing local artifact routes.

### Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/projects/{projectId}/review-tasks?status=&tier=&chapterId=` | Ranked task list (priority-ordered server-side, per §priority ordering algorithm) |
| `GET /api/v1/projects/{projectId}/review-tasks/{taskId}` | Full task detail including all members' evidence |
| `POST /api/v1/review-tasks/{taskId}/resolve` | Apply a single resolution action to one member (`{memberSegmentId, action, params}`) |
| `POST /api/v1/review-tasks/{taskId}/resolve-bulk` | Apply a task's bulk action to every member (`{action}`) |
| `GET /api/v1/projects/{projectId}/chapters/{chapterId}/skim-playlist?n=20` | The skim-mode playlist: ordered clip list with `{segmentId, startMs, endMs, contextSegmentIds, taskId}` per clip, built per §Skim mode's selection algorithm |
| `POST /api/v1/projects/{projectId}/chapters/{chapterId}/approve` | Records a `human` approval for the chapter's current active render (existing v1 endpoint, semantics unchanged) |
| `PATCH /api/v1/projects/{projectId}/production-settings` | Gains `autoApprovalPolicy: boolean` (existing endpoint, additive field) |
| `POST /api/v1/projects/{projectId}/segments/{segmentId}/renders/{renderId}/revert` | Creates a new append-only render record pointing at `renderId`'s artifact, tagged `revertOf` (§Undo model) |

### Spot-fix priority flag on render requests

`GenerateSegmentRequest` (existing schema, `POST …/segments/{segmentId}/render` and the patch
endpoint) gains one additive field:

```json
{
  "voiceProfileId": "…",
  "direction": { "…": "…" },
  "priority": "spot_fix"   // new, optional, defaults to "background"
}
```

The job orchestrator's worker pool ([target-architecture.md](../../architecture/target-architecture.md))
treats this as a priority-queue key: any `spot_fix` request is dequeued ahead of any queued
`background` request, regardless of arrival order, so an interactive fix never waits behind a
book's worth of production rendering. This is the only orchestration change this document
requires; everything else about rendering (caching, QA, artifact layout) is unchanged.

## Metrics

Review burden must be measured locally — the same discipline
[product-vision-v2.md](../../product/product-vision-v2.md) §9 applies to the rest of the
product — so the `< 20 tasks/book` and `≤ 1 hour chosen review` targets are verified, not
assumed.

| Metric | Definition | How measured | Feeds |
|---|---|---|---|
| Tasks per book | Count of distinct `review_tasks` rows ever created for a project (any status) | `COUNT(review_tasks) WHERE project_id = …` | [product-vision-v2.md](../../product/product-vision-v2.md) §5.2 `< 20` target |
| Open tasks at export time | Count of `review_tasks` with `status = open` when export succeeds | Same table, filtered, sampled at export | Confirms zero-touch rule 1 (export never required tasks to be open — or zero) |
| Fixes per book | Count of resolution actions (`resolve`/`resolve-bulk` calls) applied by a human, excluding `auto_resolved_by_rerun` | Count of segment patches tagged with a `sourceTaskId` | Distinguishes human effort from pipeline self-correction |
| Time-in-review | Wall-clock from first chapter-review-route open to last review-related action (task resolve, approval, revert) for a project, per session | Local session timestamps (no manuscript content, per the vision doc's local-only telemetry rule) | `≤ 1 hour typical chosen review` goal |
| Skim-mode adoption | Share of review sessions that use skim mode vs. straight-through listening | Local interaction counts | Validates whether skim mode is actually the fast path it's designed to be |
| Spot-fix latency (p50/p95) | Wall-clock from patch request to playback resume | Client-side timing around the spot-fix loop's re-render step | `< 15s` budget verification |
| Task reopen rate | Share of `resolved`/`auto_resolved_by_rerun` tasks that later reopen | `review_tasks` state transitions | Signals whether resolution actions are durable or whether the pipeline is contradicting human calls too often |

All of the above are local-only, per-run measurements a user can inspect and clear, consistent
with [product-vision-v2.md](../../product/product-vision-v2.md) §9's telemetry stance — no
manuscript content leaves the machine, and none of this is a condition of use.

## Migration path from review-patch-workbench

`review-patch-workbench.md`'s six-plus-pane `SegmentReviewInspector` does not disappear — it
becomes the content of the Inspector **drawer** (never inline), reached by tapping a
transcript line or a task member, per
[frontend-architecture.md](../../ui/frontend-architecture.md)'s `/review/[chapterId]` route and
[design-system.md](../../ui/design-system.md)'s progressive-disclosure rules. Pane-by-pane
disposition:

| v1 inspector pane | v2 disposition |
|---|---|
| Source and canonical text | Survives, unchanged — first thing in the drawer |
| Structure and parser warning summary | Replaced by the task's evidence block when the segment is a task member; otherwise omitted (no warning to show, per the flag-flood elimination) |
| Cast attribution and linked voice status | Survives as the "Speaker" evidence section (§Evidence inspection), now including the vote tally/candidate set from S4-v2 |
| Direction emotion/pace/intensity + lock/source metadata | Survives as the "Delivery" section, now the entry point for the flat-delivery spot-fix action (slider + re-render preview) |
| Current segment audio and waveform metadata | Survives; now also the entry point for before/after compare when a prior render exists |
| Render history, QA findings, comments, patch queue | Survives as the render-history tab, now including revert actions (§Undo model) and the compare view |
| The chapter transcript's color-coded speakers + issue markers | Survives, restyled to the monochrome marker language (§Waveform/transcript issue markers) |
| The workflow shell's single "next best action" card | Survives conceptually as the review-task ranked list's top item, surfaced on the Overview route per [frontend-architecture.md](../../ui/frontend-architecture.md) |
| "Mark listened and approved" action | Survives, semantics extended per [Chapter/book approval model v2](#chapterbook-approval-model-v2) |
| The Structure & Cast Draft "Parser Review" queue (warnings + cast issues combined) | **Retired.** Replaced entirely by the review-task list; there is no separate warnings queue to combine with anything, because warnings no longer accumulate ungrouped |
| `POST /api/v1/issues/{issueId}/apply-action` (`merge_cast`/`confirm_cast`) | Survives as the underlying mechanism a task's `cast_merge`/`cast_name` resolution actions call — the endpoint doesn't change, the UI path to it does (task-first, not issue-list-first) |

Sequencing (each step independently shippable, mirroring the incremental-migration discipline
in [frontend-architecture.md](../../ui/frontend-architecture.md)):

1. Ship `review_tasks` grouping over the *existing* v1 `issues`/`structure_parser_warnings`
   data (a task can group ungrouped v1 warnings by scene/chapter even before extraction-v2
   ships) — this alone collapses the visible queue size without waiting on the pipeline
   rewrite, and de-risks the task UI against real (if still large) v1 data.
2. Ship the listen-first player route with markers and the spot-fix loop, reading from the
   task list built in step 1.
3. Ship skim mode once step 2's player/transcript sync is stable.
4. Cut the Parser Review queue and the always-open inspector pattern once the task list and
   drawer fully cover their functionality (verified via the pane-by-pane table above).
5. Swap the task *source* from "grouped v1 warnings" to "extraction-pipeline-v2's native
   grouped tasks" as each v2 stage lands (per
   [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)'s own migration
   plan) — the UI does not need to change again at this step, since it already consumes
   `review_tasks` as an opaque ranked list; only the volume and quality of what populates that
   table changes.

## Risks & open questions

- **Grouping quality before extraction-pipeline-v2 ships.** Step 1 above groups v1's ungrouped
  warnings by scene/chapter as a stopgap. A naive grouping (e.g. "everything in this scene") on
  a genuinely bad scene could still produce a task with 40 members — better than 40 standalone
  rows, but not the "12 lines" precision the v2-native grouping achieves. *Open:* how much
  grouping-quality investment is worth making in the stopgap versus accepting a coarser
  interim experience.
- **Re-render preview cost for delivery tuning.** A debounced re-render on every emotion/
  intensity slider drag (§spot-fix loop) could still generate meaningful TTS load if a user
  drags slowly across many values. *Open:* whether the debounce window needs to be adaptive to
  observed TTS latency, or whether a cheaper proxy preview (e.g. pitch/rate-shifted playback of
  the *existing* render) should stand in before committing to a real re-render.
- **Auto-approval policy and trust.** An `auto`-approved badge could be mistaken for a human
  sign-off by someone downstream (a distributor, a co-author) who doesn't read the
  `approvalSource` field closely. *Open:* whether the export manifest needs a more prominent
  disclosure than a field value when `autoApprovalPolicy` was used for any chapter in the book.
- **Skim-mode clip boundaries across scene changes.** The ±2-context-segment window (§Skim
  mode) can straddle a scene break, producing a clip that jumps tone abruptly. *Open:* whether
  clip boundaries should clamp to scene boundaries even when that means less context on one
  side.
- **Task reopen churn during progressive/provisional delivery.** [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)'s
  progressive chapter-level delivery means a provisional cast merge in chapter 1 can be
  corrected by book-level reconciliation later, which — per §Task lifecycle — reopens a task a
  user may have already resolved and moved on from. *Open:* whether a reopened task needs a
  distinct, gentler notification treatment than a brand-new task, so early listeners aren't
  repeatedly pulled back to chapter 1.
- **Priority-score stability across sessions.** Because `priority_score` is re-derived on every
  read (not stored authoritative), two review sessions minutes apart could see tasks reorder if
  an unrelated readiness run completes between them. *Open:* whether the ranked list needs a
  session-scoped stable sort (freeze order at session start) to avoid a task appearing to "jump
  around" mid-review.
