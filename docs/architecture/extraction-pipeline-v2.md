# Extraction Pipeline v2 — LLM-First Book Understanding

This document specifies the redesigned book-understanding pipeline: the stages
that turn an imported manuscript into a structured, cast, attributed, directed
set of segments ready for [automatic casting](../pipeline/casting/automatic-casting-v2.md)
and [expressive TTS](../pipeline/tts/tts-engine-strategy.md). It is the answer to
the product owner's headline complaint: *"a 500-page book takes 5–6 hours and
still ends with thousands of flags."*

The core thesis is an inversion. Today the pipeline is **deterministic-first**
(regex/heuristics do the real work; the LLM is a sequential patch-up tool that
runs 500–1500 times in series). v2 is **LLM-first with deterministic
verification**: understanding is produced by massively parallel, cached,
resumable LLM passes, and deterministic code is demoted to (a) cheap candidate
generation that seeds prompts as *evidence*, and (b) hard verifiers that check
LLM output against inviolable invariants. Deterministic ambiguity stops being a
user-facing flag; it becomes prompt context.

This doc specifies *what* each stage does, *why*, and *how* (algorithm,
pseudocode, prompt design, schema shapes). The job runner, checkpointing model,
event push, and data-model impact are specified once in
[`target-architecture.md`](target-architecture.md); this doc references that
runner rather than re-specifying it. The current (v1) behavior it replaces is
recorded in [`current-pipeline-behavior.md`](current-pipeline-behavior.md),
[`structure-parser-v2.md`](../pipeline/structure/structure-parser-v2.md),
[`character-bible.md`](../pipeline/casting/character-bible.md), and
[`speaker-attribution.md`](../pipeline/casting/speaker-attribution.md).

## Purpose

Convert an imported manuscript into a fully understood, patchable, segment-first
production plan — chapters, scenes, segments, cast with profiles, per-segment
speaker attribution, and per-segment direction — **fast enough and clean enough
that the default experience is zero-touch**. Manual review must become the
exception, aggregated into a handful of grouped tasks, not the norm.

## Goals (explicit budgets)

These are the numbers v2 is engineered against. They are hardware-tiered; the
headline budget targets *mid-tier* consumer hardware (a 2023-class laptop:
8-core CPU, 16 GB RAM, an integrated or entry discrete GPU, running the local
Ollama runtime from the [Model Center](local-ai/model-center.md) catalog).

| Metric | v1 today | v2 target (mid-tier) | v2 target (GPU workstation) |
|---|---|---|---|
| Wall-clock, full understanding of a 500-page book (~6,995 segments) | 6h57m measured | **≤ 30–45 min** | ≤ 12 min |
| User-facing flags per book | 2,453 + 731 + hundreds of cast issues | **< 20 grouped review tasks** | < 20 |
| Speaker-attribution accuracy (labeled dialogue) | not measured | **≥ 95% precision on auto-approved rows; ≥ 90% recall of attributable dialogue** | ≥ 95% / ≥ 92% |
| Cast precision (auto-created characters that are real, distinct) | ~601 candidates / 435 dup-suspects | **≥ 98% of auto-created characters correct; ≤ 1 spurious per 50 pages** | ≥ 98% |
| Resumability | none (restart = total loss) | **per-unit checkpoint; resume loses ≤ 1 unit of work** | same |
| Re-run cost after a manuscript edit to one chapter | full re-extraction | **only affected units recomputed (cache hit elsewhere)** | same |

Supporting goals:

- **Every auto-decision is evidence-backed and reversible.** Auto-accept is not
  "trust me"; it is "here is the window, the candidates, the votes, and the
  confidence — reviewable after the fact."
- **Progressive delivery.** Chapter 1 is fully processed and playable long
  before the book finishes; later book-level reconciliation patches provisional
  decisions (see §Progressive delivery).
- **Local-first.** No mandatory cloud. Everything runs on models in the Model
  Center catalog. Cloud can only ever be an optional accelerator.

## Non-goals

- Re-specifying the job orchestrator, DAG, checkpoint store, or event push —
  owned by [`target-architecture.md`](target-architecture.md).
- Voice selection / matching — owned by
  [`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md). v2
  extraction *produces the character profiles that feed it*.
- TTS synthesis and the emotion/delivery engine contract — owned by
  [`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md). v2
  produces the direction metadata that populates the contract.
- Generative ambience/music/SFX — owned by
  [`generative-sound-design.md`](../pipeline/assembly/generative-sound-design.md).
- Perfect literary interpretation. The bar is *audiobook-production-good*, not
  *scholarly-critical-edition-good*.

## Failure analysis of v1 (why it is slow and flaggy)

The measured reference run (`job_3c8fbf0189cd4c8e`) ran **6h57m** on one
500-page book, producing 6,995 segments, 601 cast candidates (435 flagged as
possible duplicates), 971 Ollama-assisted attribution rows, and **2,453 + 731 +
74** parser warnings. Three root causes:

**1. Zero intra-job concurrency; the LLM is a serial bottleneck.** The only
concurrency primitive in the API is `ThreadPoolExecutor(max_workers=2)` in
`jobs.py`, and it parallelizes *separate jobs*, not work *within* a job. Every
Ollama call is a blocking `urllib.request` POST (`local_llm.py`, `stream:false`,
`timeout=180`, `temperature=0`, `format=<json schema>`, one retry). A book fires
**500–1500 of these in strict series**. At seconds-to-tens-of-seconds each, that
alone is hours.

**2. Three sequential LLM loops, each patching deterministic output.**

- *Structure refinement* (`structure.py:_refine_hierarchy`): one `qwen3:4b` call
  per scene per 3,200-char atom batch (`LLM_REFINEMENT_BATCH_CHARS`), sequential,
  only re-grouping atoms the regex compiler already produced.
- *Cast dedup* (`cast_discovery.py`): deterministic mention extraction, then
  **one LLM adjudication per ambiguous candidate** (`_llm_merge_decision`, called
  from `_decision_for_candidate`). 601 candidates → hundreds of serial
  pairwise-style adjudications. This is O(candidates), and each one is a fresh
  round-trip.
- *Speaker attribution* (`speaker_attribution.py`): a deterministic rule cascade
  runs first; then, for `needs_review` rows only, one LLM call per 20-segment /
  5,000-char window (`SPEAKER_ATTRIBUTION_BATCH_SEGMENTS`,
  `SPEAKER_ATTRIBUTION_BATCH_CHARS`), sequential.

The LLM never *drives*; it *repairs*. So its ceiling is bounded by whatever the
regexes handed it, and its cost is paid one blocking call at a time.

**3. Flag-flood-by-design.** Because deterministic rules produce the primary
decision, every place a rule is *unsure* becomes a durable, per-segment,
user-facing artifact: 2,453 "Dialogue segment has no speaker attribution" + 731
"low confidence speaker" warnings, plus 74 unbalanced-quote warnings, plus
hundreds of cast duplicate issues. There is no calibrated confidence model and
no aggregation — the review queue is a firehose of per-segment findings. The UI
then melts trying to render thousands of them
([research report D](current-pipeline-behavior.md)).

Corollaries also worth fixing: PDF OCR is sequential (one `pdftoppm` +
`tesseract` per page, capped at 150 pages), and jobs are **not resumable** — a
restart marks RUNNING jobs FAILED and the 6h57m is lost.

The design principle that follows: **make the LLM the primary reasoner, run it
in parallel, cache it, verify its output deterministically, and only surface a
flag when the model itself is genuinely uncertain after voting.**

## Pipeline v2 stage graph

Each stage fans out into independent **units of work** (the checkpoint/resume
granularity from [`target-architecture.md`](target-architecture.md)). A unit is
the smallest thing that can be cached, retried, and resumed on its own. The
runner schedules units across a pool of `P` LLM workers plus a pool of OS
subprocess workers; stages are a DAG, and units within a map stage have no
ordering dependency.

```
 IMPORT (source bytes)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S1  INGESTION v2                              unit = 1 page               │
│     per-page OCR/extract (subprocess pool) ──► per-page quality score     │
│     front/back-matter classify (LLM)          unit = 1 candidate block    │
│  ► canonical.md + page_manifest + ingestion_manifest                      │
└─────────────────────────────────────────────────────────────────────────┘
    │  canonical text + page/offset map
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S2  STRUCTURE v2                              unit = 1 text chunk (~8k)   │
│     det. candidates (evidence)                                            │
│        │                                                                  │
│        ▼   MAP: LLM structure per chunk (parallel, P workers)             │
│        ▼   REDUCE: 1 LLM reconciliation over chunk-boundary seams         │
│        ▼   VERIFY: coverage invariant (every char → exactly 1 segment)    │
│        ▼   REPAIR loop on verify failure                                  │
│  ► chapters / scenes / segments + structure_manifest                      │
└─────────────────────────────────────────────────────────────────────────┘
    │  segments (atomic units, offset-preserving)
    ├───────────────────────────────┐
    ▼                               ▼
┌───────────────────────────┐   (scene windows reused downstream)
│ S3  CAST DISCOVERY v2      │       unit = 1 scene-window (MAP)
│  MAP: mentions per window  │       unit = 1 cluster (RECONCILE)
│  CLUSTER: embed + string   │
│  RECONCILE: 1 LLM / cluster│
│  PROFILE: 1 LLM / character│  ──► casting_manifest (profiles feed casting)
└───────────────────────────┘
    │  cast + provisional roster per scene
    ▼
┌───────────────────────────────────────────────────────────────────────┐
│ S4  SPEAKER ATTRIBUTION v2                     unit = 1 scene-window     │
│     det. cascade = fast PRE-PASS (candidates+evidence into prompt)      │
│     MAP: LLM attribution per window (parallel) + conversation state     │
│     low-confidence windows: self-consistency vote (k samples)           │
│     REDUCE: book-level consistency + alternation repair                 │
│  ► speaker_attributions (1 row / segment) + attribution_manifest        │
└───────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────────────────────┐
│ S5  DIRECTION / EMOTION v2                     unit = 1 scene-window     │
│     MAP: LLM direction per window (reuses S4 window + roster)           │
│  ► per-segment DirectionProfile + direction_manifest                    │
└───────────────────────────────────────────────────────────────────────┘
    │
    ▼   feeds automatic-casting-v2 + tts-engine-strategy
```

The runner materializes each stage's output as a durable **manifest** (hard
constraint) and each unit's LLM I/O as content-addressed cache entries
(§Performance engineering). S3, S4, and S5 all consume the same **scene-window**
partition, so the windows are computed once and reused.

## Stage designs

Conventions used below: `LLM.small` = the fast tier (`qwen3:4b`,
`qwen3_4b_ollama` in the catalog); `LLM.large` = the reconciliation tier (a
larger local model registered in the catalog, e.g. a `qwen3:14b`/`qwen3:32b`
class entry — see §Model tiering). `EMBED` = `qwen3-embedding` via Ollama
`/api/embed`. All LLM calls are JSON-schema-constrained (`format=<schema>`,
`temperature=0` unless sampling for a vote), matching the existing `local_llm.py`
contract, and every call writes a `llm_runs` row + prompt/response artifact.

### S1. Ingestion v2

**What.** Turn source bytes (TXT/MD/DOCX/EPUB/PDF) into clean canonical text
plus a per-page quality map and a front/back-matter classification, preserving
offset↔page mappings.

**Why.** v1 OCRs pages one subprocess at a time (capped at 150 pages) and treats
front/back matter with regex heading rules that misfire on real books. Ingestion
quality is upstream of everything; garbage OCR becomes garbage attribution.

**How.**

*Per-page extraction (unit = 1 page, OS subprocess pool of size `Q`).* For a
PDF, first attempt embedded-text extraction (`pypdf`). If a page's embedded text
is below the text-density threshold, render it (`pdftoppm`) and OCR it
(`tesseract`). These are independent per page, so they run on a bounded
subprocess pool instead of a serial loop. Remove the 150-page cap; the cap
becomes a memory-bounded queue depth.

```
def ingest_pdf(pdf, Q):
    pages = pypdf.pages(pdf)
    results = parallel_map(pool=subprocess_pool(Q), items=pages, fn=extract_page)
    return assemble_canonical(sorted(results, key=page_index))

def extract_page(page):
    embedded = page.extract_text()
    if text_density(embedded) >= MIN_DENSITY:
        return PageResult(page.index, embedded, method="embedded",
                          quality=score_quality(embedded, ocr=False))
    img  = pdftoppm(page)            # subprocess
    ocr  = tesseract(img)           # subprocess, emits text + per-word conf
    return PageResult(page.index, ocr.text, method="ocr",
                      quality=score_quality(ocr.text, ocr=True, conf=ocr.word_conf))
```

*Per-page quality scoring.* A deterministic `0..1` score per page from: mean OCR
word confidence, dictionary-hit ratio, ratio of non-word glyph runs, line-length
regularity, and hyphenation-repair count. Low-quality pages are marked in the
page manifest and can be re-OCRed at higher DPI or routed to a vision model in a
later phase; they do **not** silently pollute canonical text.

*Front/back-matter classification (unit = 1 candidate block, `LLM.small`).*
Instead of regex heading rules, segment the document into leading/trailing
candidate blocks (title page, copyright, dedication, TOC, acknowledgments, "about
the author", indexes) and classify each with **one** LLM call. Interior blocks
are not sent — only the O(10) blocks at the head/tail of the book, so this is a
handful of calls, fully parallel.

Prompt-design notes: give the model the block text (truncated), its position
(page range, distance from start/end), and ask for a label from a fixed
enum + a `read_aloud: bool`. Front/back matter is retained in canonical text but
tagged so downstream stages and the narrator can skip or specially handle it.

*I/O manifest shape* (`ingestion_manifest.json`, additive to the existing source
manifest):

```json
{
  "manifestVersion": "ingestion-v2",
  "sourceId": "src_…",
  "canonicalPath": "source/canonical.md",
  "pages": [
    {"index": 12, "method": "ocr", "quality": 0.71, "wordConfMean": 0.83,
     "canonicalSpan": [40211, 42980], "warnings": ["low_quality_ocr"]}
  ],
  "matter": [
    {"blockId": "sha1…", "label": "copyright", "readAloud": false,
     "canonicalSpan": [0, 1180], "confidence": 0.98, "llmRunId": "run_…"}
  ],
  "quality": {"pageCount": 512, "ocrPageCount": 61, "meanQuality": 0.94,
              "lowQualityPages": 7}
}
```

### S2. Structure v2

**What.** Detect chapters, scenes, and build renderable **segments** — the
atomic editable/renderable unit (hard constraint) — with every source character
covered by exactly one segment.

**Why.** v1 trusts regexes (`EXPLICIT_CHAPTER_RE`, separator lines, quote
atomization) for the *decision* and uses the LLM only to re-group atoms within a
scene. Regexes miss unconventional chapter styling, run-in scene breaks, and
epistolary/verse structure, and they never see enough context. v2 uses
deterministic detection as **evidence** and lets the LLM decide, then verifies
the decision deterministically.

**How — map/reduce with a hard coverage verifier.**

*Chunking (unit = 1 text chunk).* Split canonical text into ~8,000-char chunks
on paragraph boundaries with a ~500-char overlap so chunk seams never fall inside
a paragraph. Chunk size is tuned so one chunk + prompt fits comfortably in the
small model's context with room for output.

*Deterministic evidence pass.* Run the cheap detectors (the existing
`StructureCompiler` signals: heading regexes, container signals from DOCX/EPUB,
separator lines, quote-aware atom boundaries) and attach them to each chunk as
*hints*, not decisions. Container signals (DOCX heading styles, EPUB spine/TOC)
remain high-trust evidence and are passed as strong priors.

*MAP (parallel, `LLM.small`, one call per chunk).* For each chunk the model
returns a structural parse over the chunk's character offsets: chapter/scene
boundaries and a segment list, each segment typed
(`narration`/`dialogue`/`dialogue_with_tag`/`action_beat`/`heading`/`footnote`)
and carrying its `[start,end]` offsets **relative to the chunk**, which the
runner rebases to absolute source offsets.

Prompt-design notes:
- The model returns **offsets and labels only — never manuscript text** (same
  safety rule as v1's atom grouping). This keeps output tiny and makes the
  coverage verifier possible.
- Include the deterministic hints ("a `Chapter` heading regex fired at offset
  X"; "a container `docx_heading` signal at Y") so the model can confirm or
  override with a reason.
- Include the last ~300 chars of the previous chunk as read-only context so the
  model can decide whether this chunk *continues* the previous segment.

*REDUCE (one `LLM.large` call over seams).* Chunk boundaries are the only place
the map pass can disagree with itself (e.g. a segment split across a seam, or a
chapter heading detected twice). Collect the boundary-adjacent segments from all
chunks (a small set, O(#chunks)) and run one reconciliation call that merges
seam-split segments and dedupes boundary chapters/scenes. This is O(1) LLM calls
in book size, not O(segments).

*VERIFY (deterministic, mandatory).* The coverage invariant: sort all segment
spans; assert they **partition** the readable canonical range — every source
character maps to exactly one segment, no gaps, no overlaps, monotonic order.
Also assert: segment char length ≤ `maxSegmentChars`; every chapter/scene span
contains ≥ 1 segment; offsets are in-bounds.

```
def verify_structure(segments, canonical_len):
    spans = sorted((s.start, s.end, s.id) for s in segments)
    cursor, gaps, overlaps = 0, [], []
    for start, end, sid in spans:
        if start > cursor: gaps.append((cursor, start))
        elif start < cursor: overlaps.append((start, cursor, sid))
        cursor = max(cursor, end)
    if cursor < canonical_len: gaps.append((cursor, canonical_len))
    return VerifyResult(ok=not gaps and not overlaps, gaps=gaps, overlaps=overlaps)
```

*REPAIR loop.* On verify failure, do **not** flag the user. Deterministically
patch what is unambiguous (a single gap becomes its own narration segment; an
overlap is resolved to the earlier segment) and re-verify. If a repair is
ambiguous, re-prompt only the affected chunk(s) with the specific failure
described, bounded to 2 attempts. Only if that still fails does the affected
*span* (not each segment) become one grouped review task. In practice coverage
failures are rare because the model returns offsets over text it was given.

*Segmentation rules* (deterministic, applied after verify): overlong sentences
are split on clause/prosody boundaries (carried over from v1's
`prosody_clause_split`); multi-paragraph dialogue stays one segment; footnotes
route to `footnote` production segments. Locked segments from a prior run are
carried forward verbatim (hard patchability constraint) and their spans are
masked out of the MAP input.

*I/O manifest shape* (`structure_manifest.json`, `payload.quality` retained for
API compatibility):

```json
{
  "manifestVersion": "structure-v2",
  "coverage": {"ok": true, "gaps": 0, "overlaps": 0, "repairAttempts": 0},
  "chapters": [{"id":"…","title":"Chapter One","span":[1180,40211],
                "source":"llm","evidence":{"regex":true,"container":"docx_heading"}}],
  "segments": [{"id":"…","chapterId":"…","sceneId":"…","span":[1180,1520],
                "type":"dialogue_with_tag","llmRunId":"run_…"}],
  "quality": {"chapters":38,"scenes":too_many_to_list,"segments":6412,
              "reviewTasks":0}
}
```

### S3. Cast discovery v2

**What.** Discover the cast, resolve aliases to distinct characters, and
synthesize a profile per character (role, gender, age, traits, speech style,
relationships). These profiles are the direct input to
[`automatic-casting-v2.md`](../pipeline/casting/automatic-casting-v2.md).

**Why.** v1's fatal move is **per-candidate adjudication**: mention extraction
produces 601 candidates, then the LLM is called once per ambiguous candidate to
decide merges (`_llm_merge_decision`). That is O(candidates) serial calls and it
still leaves 435 duplicate-suspect issues because pairwise deterministic
shortlisting (`CharacterIndex.shortlist(limit=5)`, `SAFE_SHORTLIST_SCORE`) can't
see the global picture. v2 replaces adjudication with **clustering**: group all
mentions first, then reconcile *once per cluster*.

**How — map / cluster / reconcile / profile.**

*MAP (parallel, `LLM.small`, unit = 1 scene-window).* Reuse the S2 scene-window
partition (the v1 `CAST_WINDOW_MAX_CHARS = 6000`, `CAST_WINDOW_OVERLAP_SEGMENTS =
1` bounds are a fine starting point). For each window, one call extracts mention
records: surface name, any title/honorific, apparent role, pronouns used,
speaking-vs-mentioned, and a short evidence quote. Deterministic name regexes run
too and are folded in as additional mentions (they seed, they don't gate).

*CLUSTER (deterministic + embeddings, one pass, no per-pair LLM).* Cluster
mentions into candidate characters using a combination of:
- **String features:** normalized-name exact match, honorific-stripped match,
  initial/surname compatibility, edit distance for spelling variants.
- **Embeddings:** embed each distinct surface form + its aggregated evidence
  context with `qwen3-embedding`; cosine similarity captures "the captain" ↔
  "Captain Reyes" ↔ "Reyes" that string features miss.
- **Co-reference constraints:** two forms that co-occur as *distinct* speakers in
  the same window cannot be the same character (a cannot-link constraint).

Run agglomerative clustering with the cannot-link constraints and a similarity
threshold tuned on the eval set (§Quality evaluation). Output: clusters, each a
provisional character with all its aliases and pooled evidence.

```
mentions = flatten(parallel_map(scene_windows, extract_mentions))     # LLM.small
forms    = dedupe_surface_forms(mentions)
vecs     = EMBED([f.text + " ‖ " + f.context for f in forms])         # 1 batched embed call/window
sim      = combine(string_features(forms), cosine(vecs))              # weighted
clusters = constrained_agglomerative(forms, sim, cannot_link=cooccurrence_conflicts(mentions),
                                     threshold=TAU_CLUSTER)
```

*RECONCILE (one `LLM.large` call per cluster — not per candidate).* For each
cluster, one call is asked to: confirm the members are one character (or split
into N), pick the canonical display name, and flag genuine ambiguity. Because
clusters are already tight, most reconcile calls are trivial confirmations, and
their count is O(distinct characters) ≈ dozens, **not** O(mentions) ≈ hundreds.
Prior project rulings (confirmed/rejected merges, user locks — the durable
[Character Bible](../pipeline/casting/character-bible.md) mention ledger) are
passed in and always win, preserving append-only/patchable history.

*PROFILE (one `LLM.small` call per confirmed character).* Synthesize the
production profile from the character's pooled evidence windows:

```json
{
  "characterId": "chr_…",
  "displayName": "Captain Reyes",
  "aliases": ["Reyes", "the captain", "Elena"],
  "role": "protagonist",
  "gender": "feminine",
  "ageBand": "adult",
  "traits": ["authoritative", "weary", "dry-humored"],
  "speechStyle": {"register": "formal", "verbosity": "terse",
                  "accentHint": "none", "tics": ["clipped commands"]},
  "relationships": [{"characterId": "chr_…", "type": "commands"}],
  "evidenceWindowIds": ["win_…", "win_…"],
  "confidence": 0.93
}
```

These fields map directly onto casting's matching algorithm (gender/age/register
→ voice facets) and TTS direction defaults (speech style → baseline
DirectionProfile), so no downstream stage has to re-derive them.

*I/O.* `casting_manifest.json` (existing handoff) gains a `profiles` array and a
`clusters` diagnostic block (which surface forms merged, with similarity scores)
so reconciliation is auditable. The durable mention ledger and merge/split
history are preserved exactly as
[`character-bible.md`](../pipeline/casting/character-bible.md) specifies.

### S4. Speaker attribution v2

**What.** Write one `speaker_attributions` row per segment (hard: one per
segment), attributing dialogue (and narration) to a character or the narrator,
with calibrated confidence.

**Why.** This is where v1 generates the most flags (2,453 + 731). v1 runs a
deterministic cascade as the *primary* method and calls the LLM only to mop up
`needs_review` rows, serially, one 20-segment window at a time. v2 makes the
**LLM the primary attributor**, runs windows in parallel, and demotes the
deterministic cascade to a **fast pre-pass** whose outputs become prompt
evidence — plus book-level consistency and voting so uncertainty is resolved,
not flagged.

**How.**

*Pre-pass (deterministic, cheap, no LLM).* Run the existing cascade (parser
`Name:`/quote-tag/inverted-tag/action-beat candidates, nearby-turn, speech-action
cue, pronoun coreference, two-speaker alternation/interruption/vocative). Its job
is no longer to *decide*; it produces, per segment, a ranked candidate list + the
active-speaker roster for the scene. High-confidence, unambiguous rows (e.g. an
explicit `"…," said Reyes` tag) can still auto-resolve without an LLM call — they
short-circuit for speed — but everything else flows into the LLM as evidence.

*MAP (parallel, `LLM.small`, unit = 1 scene-window).* For each scene-window, one
call attributes every `TARGET` dialogue/narration segment. The prompt carries:
- the window's segments (marked `TARGET` vs `CONTEXT`, as v1 already does),
- the **active-speaker roster** with character profiles from S3 (so the model
  reasons about *known* characters, not free-form names),
- the deterministic candidates per segment as suggestions with their reasons,
- up to 5 reviewer-confirmed examples from earlier in the book (compounding
  corrections — carried from v1),
- an incoming **conversation state** (see below).

Output per TARGET segment: `characterId | "narrator" | "unknown"`, a
`confidence` in `0..1`, and a one-line rationale. Only TARGET IDs are accepted
back; CONTEXT is evidence only.

*Conversation-state tracking.* Windows within a scene are processed with a
carried state: `{lastSpeaker, turnParity, openAddressee, activeRoster}`. Because
alternation ("A, then B, then A…") is the single most common attribution pattern,
the state lets a window resolve unmarked turns from the previous window's
resolution. State is threaded through the *reduce* pass (below), so scene-window
MAP calls can still run in parallel — the state passed in is the deterministic
pre-pass estimate, and the reduce pass corrects it globally.

*Self-consistency voting for low-confidence windows (instead of flagging).* If a
window returns any TARGET below the mid confidence threshold, resample that
window `k` times (e.g. `k=3`, `temperature≈0.4`) and take the **majority**
attribution per segment. Agreement across samples raises confidence to
auto-accept; genuine disagreement is what finally becomes a flag. This converts
most former "low confidence speaker" warnings into resolved decisions at the cost
of a few extra calls only on the hard windows.

```
for w in scene_windows:                        # parallel
    a = LLM.small(attr_prompt(w, roster, profiles, det_candidates(w), state0(w)))
    lows = [t for t in a.targets if t.confidence < MID]
    if lows:
        samples = [LLM.small(attr_prompt(w, …), temperature=0.4) for _ in range(k)]
        a = merge_majority(a, samples)          # vote only on low-confidence targets
    emit(a)
```

*REDUCE — book-level consistency pass (one bounded pass).* After all windows,
run a consistency reconciliation:
- **Alternation repair:** within each scene, detect broken A/B/A alternation and
  repair the odd row out when the surrounding rows agree and the roster is
  two-speaker (deterministic; the LLM is consulted only on residual conflicts).
- **Dialogue-habit consistency:** aggregate each character's attributed lines;
  if a line's style is a strong outlier for its assigned character but a perfect
  fit for another active character, mark for the reconciliation call.
- **Cross-window state stitching:** apply the true conversation state across
  window seams (the seam is the only place MAP's parallel `state0` estimate can
  be wrong).

Residual conflicts from all three feed **one** `LLM.large` reconciliation call
per scene (small input: only the conflicting rows + evidence), not per segment.

*Confidence calibration.* See §Confidence & flag model — attribution is the
primary consumer of the three-tier policy.

*I/O.* `attribution_manifest.json` records per-row: method
(`llm` / `det_shortcircuit` / `vote` / `reduce_repair` / `propagated`),
confidence, the window id, the candidate set considered, and (for votes) the
sample tally. Rows remain patchable with sibling propagation exactly as
[`speaker-attribution.md`](../pipeline/casting/speaker-attribution.md) specifies;
`userLocked` rows are never overwritten.

### S5. Direction / emotion inference v2

**What.** Produce a per-segment `DirectionProfile`
(pace/intensity/tone/emotion/pauses/style_prompt/emphasis/whisper) that populates
the expressive-TTS contract.

**Why.** v1 infers direction with keyword heuristics + an optional serial LLM
pass, and — critically — most of the profile is metadata-only because no engine
consumes it (research report C). v2 produces *richer, engine-aligned* direction
in the same parallel window framework, so it is ready the day
[`tts-engine-strategy.md`](../pipeline/tts/tts-engine-strategy.md)'s expressive
engines land.

**How.** Reuse the S4 scene-window partition and its resolved speaker roster
(direction depends on *who* is speaking and their profile's baseline style). One
`LLM.small` call per window returns, per segment: emotion (from the controlled
vocabulary: neutral, warm, tense, quiet, urgent, somber, bright, fearful,
angry), intensity, pace, pause-before/after hints, emphasis spans, and an
optional free-text `style_prompt` for engines that accept one. The character's
S3 speech-style profile seeds the baseline so direction expresses *deviation
from* the character's norm (a normally-terse character shouting reads
differently than a verbose one shouting).

Deterministic verification: emotion/tone must be in the controlled vocabulary;
numeric fields clamped to DirectionProfile bounds; pause ms within `0..5000`.
Output feeds the direction→engine contract; unsupported controls per engine are
still recorded as `unsupportedDirection` (honest degradation, as today).

*I/O.* `direction_manifest.json`, one entry per segment, each with its `llmRunId`
and the roster/profile inputs used.

## Confidence & flag model

The single most important behavioral change. **Flags are rare and meaningful;
every auto-decision is evidence-backed and reviewable after the fact.**

**Three-tier policy** (applied uniformly to structure repairs, cast
reconciliation, attribution rows, and direction — thresholds per stage):

| Tier | Condition | Action |
|---|---|---|
| **Auto-accept** | `confidence ≥ HIGH` | Apply silently. Keep full evidence (window, candidates, votes, `llmRunId`) so it is auditable but not queued. |
| **Auto-accept with audit trail** | `MID ≤ confidence < HIGH` | Apply, but tag `autoAccepted=true` and include in an optional "spot-check" view. Not a blocking flag. |
| **Flag** | `confidence < MID` **after** voting/reconciliation | Do not apply a guess; open a grouped review task. |

**Aggregation — never thousands of per-segment warnings.** Flags are grouped
into a handful of durable review tasks keyed by cause, so the review queue is
small even when a book is genuinely hard:

- *per character:* "3 characters need a name confirmation" (from S3 reconcile).
- *per scene/chapter:* "Chapter 12: 4 dialogue turns are ambiguous between Reyes
  and Okonkwo" (from S4 vote disagreement).
- *per span:* "1 structural span in Chapter 3 could not be segmented cleanly."

Each grouped task carries the evidence for every member so a reviewer resolves a
cluster of related decisions in one action, and confirmations **propagate** (a
confirmed speaker propagates to sibling rows, an existing behavior). The budget
(< 20 tasks/book) is a design constraint on threshold calibration, not a hope.

**Calibration.** Thresholds (`HIGH`, `MID`, per stage) are not guessed; they are
fit against the labeled eval set (§Quality evaluation):

1. Run the stage on the golden fixtures, recording model confidence and
   correctness for every decision.
2. Build a reliability curve (predicted confidence vs empirical accuracy) and
   apply isotonic/Platt calibration so a reported `0.9` really means ~90%
   correct.
3. Choose `HIGH` as the lowest calibrated confidence whose auto-accept precision
   meets the goal (≥ 95% for attribution). Choose `MID` so the flag *volume*
   lands under budget while flag *precision* (a flagged item really is
   ambiguous) stays high.
4. Store the fitted mapping per model + stage in the repo so calibration is
   reproducible and versioned; re-fit when the model tier changes.

Voting interacts with calibration: agreement across `k` samples is itself a
strong calibrated signal, so post-vote confidence uses the vote margin, not just
the single-sample score.

## Performance engineering

**Concurrency math (worked example, mid-tier target).** Take the reference book:
~6,995 segments. The dominant cost is the LLM window passes. Using scene windows
of ~15 segments, that is ~470 windows for S4 and ~470 for S5, plus ~470 for S3
map, plus ~600 chunks for S2 — call it **~2,000 primary LLM units**, plus a small
number of reduce/reconcile/profile calls.

Let `T` = mean small-model window latency and `P` = parallel LLM workers.
Wall-clock ≈ `(units × T) / P` (+ reduce tail + non-LLM stages).

```
units ≈ 2000
T     ≈ 4 s   (small model, short JSON output, warm)
P     ≈ 4     (mid-tier: 4 concurrent Ollama requests within RAM budget)

wall_clock ≈ 2000 × 4 / 4 = 2000 s ≈ 33 min          → within the 30–45 min budget
```

Voting adds calls only on hard windows (say 15% of S4 windows × k=3 extra ≈ 210
calls ≈ +3.5 min at P=4). Reduce/reconcile/profile are O(chapters+characters) ≈
low hundreds of `LLM.large` calls; the large model is slower but there are far
fewer, and it overlaps other stages. Ingestion OCR runs on its own subprocess
pool `Q` concurrently with nothing blocking it. On a GPU workstation `T` drops to
~1 s and `P` rises to 8–16, giving the ≤ 12 min figure.

The point: v2 hits the budget by turning **2000 serial calls (hours)** into
**2000/P concurrent calls (minutes)** — the same model, the same prompts, just
not one-at-a-time.

**Prompt/result caching (content-addressed).** Cache key = `sha256(model_id +
stage + schema_version + normalized_prompt)`. Because prompts are built from
canonical text spans + roster + profiles, an unchanged span yields an identical
key → cache hit. Editing one chapter invalidates only the windows whose spans
overlap the edit; the rest of the book is served from cache on re-run. This is
what makes patch-time re-extraction cheap (goal: only affected units recomputed).
Cache lives on the filesystem (never audio-in-DB; here it's LLM JSON, also
filesystem-backed), keyed alongside the existing `llm_runs` artifacts.

**Batching multiple windows per prompt (where quality allows).** For *easy*
stages (S5 direction, S3 mention extraction) several small adjacent windows can
be packed into one prompt with clearly delimited sections, cutting per-call
overhead. Measure on the eval set: batch only while accuracy is unchanged; never
batch S4 attribution beyond a scene (cross-scene batching erodes conversation
state). Batching trades a little accuracy headroom for fewer round-trips.

**Model tiering (tie to the Model Center catalog).**

| Tier | Model (catalog key) | Used for |
|---|---|---|
| small/fast | `qwen3:4b` (`qwen3_4b_ollama`) | all MAP passes (S2 chunk parse, S3 mentions, S4 attribution, S5 direction), voting |
| large/reconcile | larger local model registered in catalog (e.g. `qwen3:14b`/`32b` class) | REDUCE/RECONCILE only (S2 seams, S3 clusters, S4 residual conflicts) |
| embeddings | `qwen3-embedding` | S3 alias clustering |

Adding the large tier is a Model Center catalog entry (declared capability,
size, license, consent) plus an install job — no new runtime. On hardware that
can't host the large model, reconciliation falls back to the small model with
tighter thresholds (honest degradation, more flags, still correct).

**Checkpoint / resume per unit.** Each unit's result is committed to its manifest
+ cache as it completes; the runner records unit-level completion in the job
checkpoint store from [`target-architecture.md`](target-architecture.md). A crash
or restart resumes from the last completed unit — worst case one window (~`T`
seconds) is redone, versus v1's total loss of a 6h57m job.

## Progressive chapter-level delivery

The stage graph is a DAG over units, so the runner can prioritize **chapter 1's
units end-to-end first** and stream a playable result before the book finishes —
consistent with the progressive-pipeline section of
[`target-architecture.md`](target-architecture.md).

- **Provisional pass:** as soon as S2 emits chapter 1's segments, S3 runs cast
  discovery *scoped to chapter 1's windows* to build a **provisional roster**,
  then S4/S5 attribute and direct chapter 1. The user can play chapter 1 within
  minutes, with cast marked `provisional`.
- **Book-level reconciliation patches later:** as later chapters complete, S3
  reconciliation runs book-wide. A character introduced provisionally in chapter
  1 as "the captain" and later revealed as "Reyes" is merged by cluster
  reconciliation; the merge **re-points** chapter 1's attribution rows (existing
  merge-repoint behavior) and marks the affected chapter-1 segments for re-render
  if their resolved voice changed. Because attribution is patchable and
  append-only, this is a targeted patch, not a re-run.
- Provisional→confirmed transitions are themselves auditable events, not flags.

## Quality evaluation harness

Accuracy must be *measured locally*, not asserted.

**Golden fixtures.** A `test-assets/`-adjacent (git-ignored) corpus of
public-domain books (Gutenberg: dialogue-heavy novels, an epistolary work, a
verse work, a multi-POV novel) with hand-labeled samples:
- structure: gold chapter/scene boundaries + segment partition for a few chapters;
- cast: gold character list with alias groupings;
- attribution: gold speaker per dialogue segment for a labeled subset (a few
  hundred rows per book is enough to move the metrics);
- direction: a small qualitative-rated sample (inter-rater, not exact-match).

**Metrics & gates.**

| Stage | Metric | Regression gate |
|---|---|---|
| Structure | boundary F1; coverage-invariant pass rate | coverage = 100%; boundary F1 ≥ prior − 1pt |
| Cast | character precision/recall; alias-cluster purity (V-measure) | precision ≥ 0.98; no cluster-purity regression |
| Attribution | precision on auto-approved; recall of attributable dialogue; calibration error (ECE) | auto-approve precision ≥ 0.95; ECE ≤ 0.05 |
| Flags | flags per 100 pages; flag precision (flagged items really ambiguous) | ≤ 4 flags/100pp; flag precision ≥ 0.8 |
| Perf | wall-clock at fixed `P` on a reference machine | within budget band |

Runs as a local `pytest` harness (matching the repo's `uv run pytest`) with the
LLM either live (nightly) or replayed from cached fixtures (CI, deterministic).
Threshold calibration (§Confidence) consumes this same harness. A stage change
that regresses a gate blocks merge.

## Migration path from current code

Incremental, each step independently shippable, existing manifests/APIs preserved
until their replacement is proven on the eval harness.

1. **Foundations (no behavior change).** Build the content-addressed LLM cache
   and a parallel LLM-worker pool wrapping `local_llm.py`; add per-unit checkpoint
   hooks to the runner (coordinated with `target-architecture.md`). Land the eval
   harness with golden fixtures and wire current metrics as the baseline.
2. **Parallelize what exists.** Route v1's existing three LLM loops through the
   new worker pool + cache — same prompts, now concurrent and cached. This alone
   collapses the 6h57m toward the budget and de-risks the pool. No accuracy change
   expected; the harness proves it.
3. **Ingestion v2.** Move OCR to the subprocess pool; add per-page quality
   scoring; add the front/back-matter classifier. Remove the 150-page cap.
4. **Structure v2.** Add the chunk MAP + seam REDUCE + coverage VERIFY behind a
   feature flag; keep `structure_parsing.StructureCompiler` as the deterministic
   evidence provider and as fallback. Flip the flag per the harness.
5. **Cast v2.** Replace `_llm_merge_decision` per-candidate adjudication with
   embed-based clustering + per-cluster reconcile + profile synthesis. Keep the
   durable mention ledger, merge/split history, and prior-ruling gates
   (`character-bible.md`) unchanged.
6. **Attribution v2.** Invert `speaker_attribution.py`: cascade becomes the
   pre-pass; LLM window attribution becomes primary; add conversation state,
   voting, and the book-level reduce pass. Retain one-row-per-segment,
   propagation, and `userLocked` safety.
7. **Confidence & flag model.** Ship the three-tier policy + grouped review tasks;
   retire per-segment `structure_parser_warnings` firehose in favor of aggregated
   `issues`. Calibrate thresholds against the harness.
8. **Direction v2** and **progressive delivery** last, once the window framework
   and reconciliation are stable.

At every step the old path stays available behind a flag and the manifest
schemas gain a version field rather than breaking readers.

## Risks & open questions

- **Small-model reliability at scale.** 2,000 `qwen3:4b` calls will include some
  malformed/low-quality outputs. Mitigation: schema-constrained decoding (already
  in `local_llm.py`), the coverage verifier, and voting — but the malformation
  rate under load needs measuring. *Open:* the right retry/repair budget per unit.
- **Mid-tier concurrency ceiling.** `P=4` assumes 4 concurrent Ollama requests fit
  in RAM with the small model. On 8 GB machines `P` may drop to 2, doubling
  wall-clock. *Open:* auto-tuning `P` from detected RAM/VRAM; a documented
  low-memory tier that relaxes the budget.
- **Large-tier availability.** Reconciliation quality depends on a larger local
  model many users won't install. *Open:* how good is small-model reconciliation
  with tighter thresholds, and is the accuracy cliff acceptable?
- **Clustering threshold sensitivity.** One global `TAU_CLUSTER` may over-merge
  common names ("John") or under-merge nickname-heavy casts. *Open:* per-book
  adaptive thresholds vs a fixed one; how much the cannot-link constraints help.
- **Calibration transfer.** Thresholds fit on public-domain 19th/20th-century
  prose may not transfer to contemporary/genre fiction. *Open:* how broad the
  fixture corpus must be; whether per-genre calibration is worth it.
- **Progressive vs consistency tension.** Playing chapter 1 early means later
  merges can change chapter-1 voices, forcing re-renders. *Open:* how aggressively
  to defer provisional voice assignment vs the UX win of early playback.
- **Batching accuracy erosion.** Packing windows saves round-trips but can blur
  boundaries. *Open:* the safe batch size per stage, decided by the harness, not
  assumed.
