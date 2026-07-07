# Quality Evaluation v2 — The Local Offline Evaluation Harness

See also: [qa-rulebook.md](qa-rulebook.md) (runtime QA rules this doc does not replace),
[readiness-qa.md](readiness-qa.md) (per-project readiness reports),
[quality-benchmark.md](../../product/quality-benchmark.md) (the Sunday Suspense yardstick this
harness makes measurable), [product-vision-v2.md](../../product/product-vision-v2.md) (the
quality targets this harness proves or disproves),
[extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) (§Confidence & flag
model, §Quality evaluation harness — consolidated here),
[automatic-casting-v2.md](../casting/automatic-casting-v2.md) (§Quality evaluation —
consolidated here), [tts-engine-strategy.md](../tts/tts-engine-strategy.md) (§10 Bake-off
protocol — consolidated here as the general listening instrument),
[generative-sound-design.md](../assembly/generative-sound-design.md) (§Evaluation plan —
consolidated here), [frontend-architecture.md](../../ui/frontend-architecture.md) (§Performance
Verification — consolidated here), [target-architecture.md](../../architecture/target-architecture.md)
(job runner, checkpoint store, DAG this harness runs stages against),
[pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md) (the manifest envelope
fixture-manifests extend), [character-bible.md](../casting/character-bible.md),
[speaker-attribution.md](../casting/speaker-attribution.md).

## Why this document exists

Every sibling v2 document makes a quality claim: extraction promises "≥95% auto-accept
precision," casting promises "100% of speaking characters voiced, distinct from their scene
partners," TTS promises "directed emotion is audible in the render," sound design promises
"never masks the words," the frontend promises "60fps on a 7,000-segment book." Each doc, when
first drafted, sketched its own private evaluation section to back its own claim. That is how
you get five different half-specified harnesses that don't share a corpus, a report format, a
runner, or a CI story — and, in practice, get built by nobody, because "eventually add an eval
section" is not an actionable task in five separate places.

This document is the one harness. It answers, for every quality number anyone writes in this
suite: *what corpus proves it, what formula computes it, what threshold gates a merge on it, who
runs it and when, and where the human ear still has to be the instrument.* It is written so an
engineer with no other context can build it stage by stage (§10 gives the build order).

## 1. Purpose, goals, non-goals

### Purpose

Give Echodraft a **local, reproducible, no-cloud measurement system** that:

1. turns every numeric quality target in the v2 suite into a runnable check against known-truth
   fixtures, not an assertion in a design doc;
2. gates pipeline changes on regression, so "LLM-first" and "parallelized" extraction
   ([extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)) can be shipped
   incrementally without silently regressing accuracy for speed;
3. makes confidence-threshold calibration (the three-tier auto-accept/flag policy that keeps
   manual review under 20 tasks per book) a repeatable procedure with a stored, versioned
   artifact — not a constant someone typed in once and forgot;
4. gives the human-listening layer (the one axis no automated metric can fully replace — B3/B4
   in [quality-benchmark.md](../../product/quality-benchmark.md)) a structured, durable protocol
   instead of an ad-hoc "someone listened and it sounded fine."

### Goals

- **Every v2 quality target in this suite has a measurement.** For each number in
  [product-vision-v2.md §5](../../product/product-vision-v2.md#5-quality-bar-measurable-targets)
  and each sibling doc's own targets, this document names the exact metric, formula, fixture, and
  gate that proves or disproves it.
- **Every pipeline change that touches a measured stage runs against a regression gate before
  merge.** A change that regresses a hard gate does not merge silently better-or-worse — it fails
  CI or a required local check (§6).
- **Calibration is a documented, rerunnable procedure**, not a one-time guess. Thresholds are
  versioned, stored, and re-derived on a defined trigger (§4).
- **Nothing here requires a network call or a paid API.** The harness runs entirely on local
  models and local fixtures, consistent with constraint 4 (local-first privacy). A GPU is
  *useful* for the live/nightly tier, never *required* for the fast/CI tier.
- **The corpus and the harness are reproducible from source**, even though `test-assets/` is
  git-ignored: anyone can rebuild the exact golden corpus this document specifies from a
  checked-in fetch script plus checked-in, hand-authored labels (§2).

### Non-goals

- **Not a replacement for [qa-rulebook.md](qa-rulebook.md) or [readiness-qa.md](readiness-qa.md).**
  Those are the *runtime* layer: automated checks that run on a real user's real project with no
  ground truth available, gating that one project's chapter/export approval. This document is the
  *offline, developer-time* layer: the same kinds of checks (and, for audio QA, literally the same
  code) run against fixtures with **known-correct answers**, to measure accuracy and catch
  regressions across code changes. §9 draws this boundary precisely.
- **Not a scholarly literary-fidelity benchmark.** The golden corpus is a measurement instrument
  for the pipeline's engineering claims, not a literary-analysis exercise. "Good enough for
  audiobook production" is the bar, matching every sibling doc's non-goals.
- **Not a substitute for human listening.** No automated metric here claims to fully certify
  "sounds right" (B4/B8 in the benchmark). §7 exists precisely because some quality claims can
  only be checked by a structured human panel.
- **Not specifying the job orchestrator, DAG, or checkpoint store** — that is
  [target-architecture.md](../../architecture/target-architecture.md). This document specifies how
  eval *consumes* stage inputs/outputs (via manifests), not how the runner schedules units.
- **Not a performance-tuning guide.** §3's performance metrics and §6's gates say what must hold;
  they do not prescribe how to make a stage faster (that is each stage's own doc).

## 2. The golden corpus

Two distinct fixture classes serve two distinct purposes and must not be confused:

- **The golden accuracy corpus (§2.1–2.3):** a small set of real, hand-labeled books. Used for
  every *correctness* metric — structure, cast, attribution, direction, casting, sound-design
  taste. Small on purpose (labeling is expensive); genre-diverse on purpose (calibration must not
  overfit to one prose style).
- **The synthetic performance fixture (§2.4):** one large, procedurally generated, meaning-free
  manuscript at real-book scale. Used for every *throughput/scale* metric — wall-clock, RTF, UI
  frame budgets. It has no "correct answer" to grade against; it exists purely to be big and
  structurally realistic.

### 2.1 Golden accuracy corpus — the five books

All four literary fixtures are Project Gutenberg public-domain texts, chosen to cover the
structural and stylistic edge cases the v2 pipeline claims to handle (§3 of
[extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) calls for "an epistolary
work, a verse work, a multi-POV novel"; this selection covers the equivalent ground with texts
that are also unambiguous, well-known, and small enough to hand-label completely).

| Slug | Title | Author | Gutenberg ID | Why it's in the corpus |
|---|---|---|---|---|
| `pride-and-prejudice` | Pride and Prejudice | Jane Austen | 1342 | Large ensemble cast (~30 named characters) with heavy alias/honorific variation (`Mr. Darcy` / `Darcy` / `Fitzwilliam Darcy` / `him`) — stresses cast clustering (S3) and alias resolution hardest. Dense, mostly-tagged dialogue — the attribution "easy majority" case that must stay easy. |
| `sherlock-holmes` | The Adventures of Sherlock Holmes | Arthur Conan Doyle | 1661 | A short-story collection, not a single continuous narrative — each story is its own chapter-scale unit, stressing chapter/scene boundary detection at a different grain than a novel. First-person narrator (Watson) quoting a second first-person voice (Holmes) inside dialogue — a hard narrator-vs-character attribution case. Invented client names and period vocabulary exercise pronunciation-adjacent structure parsing. |
| `the-time-machine` | The Time Machine | H. G. Wells | 35 | A frame narrative (an unnamed narrator relates the Time Traveller's first-person account) with long narration-only stretches and sparse dialogue — the deliberate low-dialogue-density counterweight to the other four, so attribution/casting metrics are not only ever measured on dialogue-rich text. |
| `earnest` | The Importance of Being Earnest | Oscar Wilde | 844 | A stage play: pure dialogue + stage directions, no narrator at all, extremely dense speaker turns (tests turn-taking/alternation logic at its hardest) and stage directions that map directly onto `DirectionProfile`-shaped annotations (tone, action, delivery) — the corpus's dedicated **direction-annotation** and **dialogue-density** fixture. |
| `modern-format-synthetic` | *(hand-authored, ~18 pages)* | Echodraft project | n/a — original work | Public-domain 19th-century prose cannot exercise modern manuscript formatting. This fixture is written in-house specifically to cover: em-dash dialogue with no quotation marks, interleaved text-message/chat-transcript scenes, footnotes, non-standard scene-break glyphs (`* * *`, `⁂`), and a chapter that switches first-person POV mid-book. Because it is original work, the full text is committed directly (no fetch step needed) — see §2.3. |

This set deliberately spans: multi-POV ensemble prose, episodic short fiction, frame-narrative
low-dialogue prose, pure-dialogue drama, and modern formatting the public-domain set cannot
otherwise cover. It intentionally leaves out epistolary and verse works from the original
extraction-pipeline-v2 wish list for the first milestone (see §10, Rollout) — those extend the
corpus later without changing the harness.

### 2.2 Per-book hand-labeled ground truth

Each book gets five label files, described below with their JSON shapes. All labels are **original
annotation work product**, not a copy of the source text, which is why they can be committed
(§2.3) even though the corpus is git-ignored.

**`chapters.json` — exhaustive, every chapter/story labeled:**

```json
{
  "bookSlug": "pride-and-prejudice",
  "labelKind": "chapters",
  "labelVersion": "1.0.0",
  "items": [
    {"index": 0, "title": "Chapter 1", "startCharOffset": 0, "endCharOffset": 4821}
  ]
}
```

**`scenes.json` — exhaustive, every scene-break labeled with the beat that justifies it:**

```json
{
  "bookSlug": "pride-and-prejudice",
  "labelKind": "scenes",
  "labelVersion": "1.0.0",
  "items": [
    {"chapterIndex": 0, "index": 0, "startCharOffset": 0, "endCharOffset": 2210,
     "breakReason": "location_change", "note": "drawing room -> the Lucases' visit"}
  ]
}
```

**`roster.json` — exhaustive cast with every alias, one entry per distinct character:**

```json
{
  "bookSlug": "pride-and-prejudice",
  "labelKind": "roster",
  "labelVersion": "1.0.0",
  "items": [
    {"canonicalName": "Fitzwilliam Darcy", "aliases": ["Mr. Darcy", "Darcy", "him", "Mr. D—"],
     "role": "major", "gender": "masculine", "notes": "narrator never uses first name until vol. 3"}
  ]
}
```

**`attribution-sample.json` — a *sampled subset*, not exhaustive (see §2.2.1 for sampling):**

```json
{
  "bookSlug": "pride-and-prejudice",
  "labelKind": "attribution_sample",
  "labelVersion": "1.0.0",
  "items": [
    {"segmentAnchor": {"chapterIndex": 17, "sceneIndex": 2, "charOffsetInScene": 1180},
     "quotedText": "\"I am perfectly convinced by it that Mr. Darcy has no defect.\"",
     "goldSpeaker": "Fitzwilliam Darcy", "ambiguous": false,
     "annotators": ["ann_a", "ann_b"], "agreement": "unanimous"},
    {"segmentAnchor": {"chapterIndex": 42, "sceneIndex": 0, "charOffsetInScene": 340},
     "quotedText": "\"You must decide for yourself.\"",
     "goldSpeaker": null, "ambiguous": true,
     "annotators": ["ann_a", "ann_b"], "agreement": "disagreement",
     "note": "two guests present, no dialogue tag, both annotators picked a different speaker"}
  ]
}
```

`goldSpeaker: null` + `ambiguous: true` is a first-class label, not a gap: a model is scored as
**correct** if it also reports low confidence / genuine ambiguity on that row, and is not
penalized for failing to out-guess two disagreeing humans (§2.2.2, annotator instructions).

**`direction-sample.json` — a small set of hand-picked scenes, multi-annotator:**

```json
{
  "bookSlug": "earnest",
  "labelKind": "direction_sample",
  "labelVersion": "1.0.0",
  "scenes": ["act1_scene1_algernon_lane"],
  "items": [
    {"segmentAnchor": {"sceneId": "act1_scene1_algernon_lane", "lineIndex": 4},
     "text": "Did you hear what I was playing, Lane?",
     "goldEmotion": ["warm", "bright"], "goldIntensity": 0.3, "goldPace": "neutral",
     "annotators": ["ann_a", "ann_b"], "interAnnotatorAgreement": "kappa_computed_separately"}
  ]
}
```

`goldEmotion` is a list because two annotators independently labeling the controlled vocabulary
sometimes both pick a defensible-but-different term; the direction metric (§3.4) accounts for this
by treating a prediction as correct if it matches **any** annotator's label, and separately reports
the annotators' own agreement as the ceiling a model cannot be fairly expected to beat.

#### 2.2.1 Sampling strategy

- **Chapters, scenes, roster: exhaustive.** These are cheap to label completely (tens to low
  hundreds of items per book) and are the backbone every other metric's segment anchors depend on
  — a sampled chapter list would make "which chapter is segment X in" ambiguous for the other four
  label files.
- **Attribution: a stratified sample of ~300–500 rows per book**, not exhaustive (a full novel has
  thousands of dialogue lines; labeling all of them does not move the metric more than a
  well-chosen sample does — this matches the "a few hundred rows per book is enough" guidance
  already given in
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#quality-evaluation-harness)).
  Stratify by:
  - **explicit-tag rows** (a `"...," said Elizabeth` pattern) — a small fixed share (~15%), since
    the deterministic cascade already gets these right and over-sampling them would inflate
    accuracy uninformatively;
  - **alternation rows** (two-speaker back-and-forth with no tag) — the largest share (~40%),
    since this is the single most common real pattern per
    [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md);
  - **multi-party rows** (3+ active speakers in scene) — (~30%), the hardest realistic case;
  - **genuinely ambiguous rows** flagged by a cheap heuristic pre-pass (no nearby name, no clear
    alternation) — the remainder (~15%), deliberately oversampled relative to their natural
    frequency because they are where auto-accept precision is actually decided.
- **Direction: 5–8 hand-picked scenes per book**, chosen for emotional variety (calm, tense,
  comedic, grief/loss, urgent) rather than at random, labeled by **two or more** annotators so
  inter-annotator agreement can be computed as the metric's ceiling (§3.4).

#### 2.2.2 Annotator instructions (summary protocol)

The full protocol lives with the corpus at
`tests/fixtures/golden-corpus/ANNOTATION_GUIDE.md` (committed alongside the labels, §2.3); its
governing rules:

1. **A scene boundary is a beat change** (location, time, or the set of present characters shifts
   materially) — not merely a paragraph or a topic shift within one continuous conversation.
   Record the `breakReason` (`location_change`, `time_skip`, `pov_shift`, `cast_change`).
2. **An alias belongs to the roster entry only if the text supports it** — record the exact
   surface form and, where feasible, the sentence it came from; do not infer an alias a careful
   reader would consider a stretch.
3. **Record disagreement, don't paper over it.** Attribution and direction samples are labeled
   independently by two annotators first; a third pass adjudicates only real disagreements. If
   adjudication still can't produce a confident single answer, the row is stored as `ambiguous`
   with `goldSpeaker: null` (attribution) rather than forced to a coin-flip pick — see the schema
   above. This is what lets the harness fairly measure "does the model know what it doesn't know,"
   which is the entire point of the auto-accept precision metric (§3.3).
4. **Never consult model output while labeling.** Labels are produced blind to any pipeline
   version's predictions, to avoid anchoring the "ground truth" on the very system being measured.
5. **Record `agreement`** (`unanimous` / `resolved` / `disagreement`) on every attribution and
   direction row — this is the raw material for the inter-annotator ceiling reported alongside
   every accuracy number (§3.3, §3.4), so "the model scored 91%" is always read next to "and humans
   agreed with each other 96% of the time on this same sample."

### 2.3 Storage: fetch script + committed labels

`test-assets/` is git-ignored (repo convention — never stage/commit/push its contents), which is
correct for raw book text and any bulky derived artifact, but wrong for the labels themselves: the
labels are **original work product** the project has invested annotator time in, not a copy of
someone else's book, so they belong in version control like any other test fixture.

```
test-assets/golden-corpus/                      # git-ignored — fetched, not committed
  pride-and-prejudice/raw/pride-and-prejudice.txt
  sherlock-holmes/raw/sherlock-holmes.txt
  the-time-machine/raw/the-time-machine.txt
  earnest/raw/earnest.txt
  */derived/                                     # live-eval-run scratch: structure/cast/attribution
                                                  # manifests actually produced by a live run,
                                                  # LLM run caches — regenerable, never committed

tests/fixtures/golden-corpus/                    # committed — original annotation work
  ANNOTATION_GUIDE.md
  pride-and-prejudice/
    meta.json                                    # {gutenbergId, checksumSha256, fetchedAt, license: "public-domain"}
    labels/
      chapters.json  scenes.json  roster.json
      attribution-sample.json  direction-sample.json
    fixture-manifests/                            # hand-corrected stage-input manifests, §5.2
      structure_manifest.fixture.json
      casting_manifest.fixture.json
  sherlock-holmes/...
  the-time-machine/...
  earnest/...
  modern-format-synthetic/
    raw/modern-format-synthetic.txt                # original text, committed directly (no fetch step)
    meta.json  labels/...  fixture-manifests/...

scripts/fetch_golden_corpus.py                    # committed — reproduces test-assets/golden-corpus/
```

`scripts/fetch_golden_corpus.py` (alongside the existing `scripts/seed_sample_project.py`
convention) is a small, dependency-free script that, per book:

1. downloads the plain-text UTF-8 Gutenberg mirror for the book's `gutenbergId`;
2. verifies the download against the **pinned SHA-256** recorded in that book's `meta.json` —
   reproducibility means "the same bytes every time," not "whatever Gutenberg serves today";
3. strips the standard Gutenberg license header/footer boilerplate (a fixed, well-known marker
   pair) so `raw/*.txt` starts at the actual book text;
4. writes the result under `test-assets/golden-corpus/{slug}/raw/`, and is a no-op (network-free)
   if a checksum-matching file is already present — so a developer who has run it once can run the
   whole harness fully offline afterward, consistent with local-first.

`modern-format-synthetic` skips the fetch step entirely: its `raw/` text is authored by the
project and committed directly under `tests/fixtures/golden-corpus/`, since — unlike the four
Gutenberg books — the text itself is original work with no separate-provenance concern.

### 2.4 Synthetic performance fixture (500-page scale, for §3.6 performance metrics only)

This fixture has no gold labels — it exists purely to be **big and structurally realistic**, not
correct. It underwrites two different kinds of performance test:

**Mode A — DB-direct seed (UI/frontend performance).** Exactly the fixture already specified in
[frontend-architecture.md §Performance Verification](../../ui/frontend-architecture.md#performance-verification):
~500 pages, ~7,000 segments, ~120 characters, ~600 mixed warnings/issues, inserted directly through
the repository layer (`apps/api/scripts/seed_large_project.py`, no LLM calls, no real extraction
run) so it is fast and deterministic in CI. This document does not duplicate that spec; it adopts
it as the shared performance fixture and cross-references it from the master gate table (§6).

**Mode B — generated manuscript text (pipeline throughput/concurrency performance).** For the
extraction pipeline's own wall-clock and concurrency-math claims
([extraction-pipeline-v2.md §Performance engineering](../../architecture/extraction-pipeline-v2.md#performance-engineering)),
a DB-seeded fixture is useless — the pipeline needs actual manuscript *text* to chunk, window, and
send through LLM/OCR calls. `scripts/generate_synthetic_manuscript.py` (proposed, new) produces
one deterministic, meaning-free ~500-page manuscript:

```python
def generate_synthetic_manuscript(pages=500, chars_per_page=1800, chapters=40,
                                   characters=120, dialogue_density=0.4, seed=20260707):
    rng = random.Random(seed)
    cast = synthesize_cast(characters, rng)          # name-bank x surname-bank, zero overlap
                                                      # with any golden-corpus character name
    out = []
    for chapter_index in range(chapters):
        out.append(chapter_heading(chapter_index))    # exercises heading-regex + LLM structure both
        for _scene in range(rng.randint(2, 5)):
            speakers = rng.sample(cast, k=rng.randint(2, 4))
            weights = zipf_weights(len(speakers))      # mirrors real dialogue-share skew, not uniform
            for _beat in range(rng.randint(8, 20)):
                if rng.random() < dialogue_density:
                    out.append(templated_dialogue_line(weighted_choice(speakers, weights), rng))
                else:
                    out.append(templated_narration_sentence(rng))
            out.append(SCENE_BREAK_GLYPH)
        out.append(CHAPTER_BREAK_GLYPH)
    inject_formatting_noise(out, rng)                  # occasional em-dash dialogue / footnote / epistolary
                                                        # insert, at low density — exercises the same
                                                        # structural edge cases as the golden corpus, at scale
    return truncate_to_char_budget("\n".join(out), pages * chars_per_page)
```

Sentence/dialogue templates are a small hand-written bank (never an LLM call — generation must be
instant, offline, and not itself become the bottleneck being measured), and the whole function is
seeded for byte-identical output across machines and CI runs. Two invocation modes:

- `uv run echodraft-eval --suite performance --book synthetic-500pg --llm replay` — every LLM/OCR
  call is served from a pre-populated content-addressed cache with canned, schema-valid responses,
  so this measures pure **orchestration overhead** (DAG scheduling, checkpoint I/O, non-LLM stage
  cost) with no model installed — safe for CI.
- `uv run echodraft-eval --suite performance --book synthetic-500pg --llm live` — real local Ollama
  calls, used on a developer/nightly machine to validate the actual wall-clock budget against the
  worked example in
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#performance-engineering)
  (~2,000 units ÷ `P` workers ≈ 30–45 min at `P=4`).

Because this fixture is meaning-free, it **never** feeds structure/cast/attribution accuracy
metrics (§3.1–3.3) — only §3.6 performance metrics. Mixing the two fixture classes would silently
corrupt an accuracy number with content nobody ever verified was structured correctly.

## 3. Metric definitions

Every metric below states its exact formula and which fixture (§2.1 golden corpus vs §2.4
synthetic fixture) it runs against. `TP`/`FP`/`FN` follow standard information-retrieval
convention: a predicted item counts as a true positive if it matches a gold item within the
stated tolerance/criterion.

### 3.1 Structure — boundary precision/recall/F1 with tolerance windows

For chapter boundaries and scene boundaries independently:

```
match(predicted_boundary, gold_boundary) := |predicted.charOffset - gold.charOffset| <= tolerance

TP = count of gold boundaries with >=1 matching predicted boundary (one-to-one, closest first)
FP = count of predicted boundaries with no matching gold boundary
FN = count of gold boundaries with no matching predicted boundary

precision = TP / (TP + FP)
recall    = TP / (TP + FN)
F1        = 2 * precision * recall / (precision + recall)
```

- **Chapter tolerance:** `tolerance = 40 chars` (chapters are announced by a heading; the offset
  should be nearly exact).
- **Scene tolerance:** `tolerance = 200 chars` (a scene break is a beat, not a byte; annotators
  themselves record a range, not a single offset — see §2.2.2).
- **Coverage-invariant pass rate** (reused verbatim from
  [extraction-pipeline-v2.md's `verify_structure`](../../architecture/extraction-pipeline-v2.md#s2-structure-v2)):
  `pass_rate = (runs where gaps == 0 and overlaps == 0) / total runs`. This is a correctness
  invariant, not a tolerance-windowed match — it must be `1.0`, always; see §6.

### 3.2 Cast — roster F1 with alias resolution, merge/split error rates

Given the gold roster (a set of canonical characters, each with a set of gold aliases) and the
predicted clusters (each a set of surface forms the pipeline believes are the same character):

```
best_match(predicted_cluster) := the gold character whose alias set has the largest
                                  token-overlap (Jaccard) with the predicted cluster's surface forms

TP = count of predicted clusters whose best_match's own best-matching predicted cluster is itself
     (a mutual best match — this is the bipartite-matching step, solvable with a simple greedy
     max-weight matching at corpus scale, no need for full Hungarian assignment here)
FP = predicted clusters with no mutual best match (spurious character)
FN = gold characters with no mutual best match (missed character)

roster_precision = TP / (TP + FP)
roster_recall    = TP / (TP + FN)
roster_F1        = 2 * roster_precision * roster_recall / (roster_precision + roster_recall)
```

- **Merge error:** a predicted cluster whose surface forms draw from **two or more distinct gold
  characters** — count of such clusters ÷ gold character count. (Two different people wrongly
  collapsed into one.)
- **Split error:** a gold character whose aliases are scattered across **two or more predicted
  clusters** — count of such gold characters ÷ gold character count. (One person wrongly split
  into two.)
- **Alias-cluster purity (V-measure):** standard clustering V-measure (harmonic mean of
  homogeneity — each predicted cluster contains only one gold character — and completeness — each
  gold character's aliases land in only one predicted cluster) computed over surface forms as
  cluster members. This is the single number that summarizes merge+split error jointly and is what
  the regression gate (§6) tracks release-over-release, since precision/recall alone can mask a
  merge-error increase offset by a split-error decrease.

### 3.3 Attribution — accuracy, auto-accept precision, recall, calibration error

Against the `attribution-sample.json` rows (§2.2), excluding rows marked `ambiguous: true` from
the primary accuracy figure (a model that also reports ambiguity there is scored separately, per
below):

```
accuracy = (rows where predicted_speaker == goldSpeaker) / (non-ambiguous rows)

auto_accept_precision = (rows in the auto-accept tier where predicted_speaker == goldSpeaker)
                          / (rows in the auto-accept tier)
     # "auto-accept tier" = confidence >= HIGH after voting/reduce (the three-tier policy in
     # extraction-pipeline-v2.md §Confidence & flag model). THIS is the metric that guards HIGH —
     # see §4, it is the single number threshold calibration is fit against.

recall_of_attributable_dialogue = (dialogue rows attributed to a named character or "narrator",
                                    i.e. not "unknown") / (dialogue rows with a non-null goldSpeaker)

ambiguity_recall = (rows where goldSpeaker is null AND predicted confidence < MID)
                    / (rows where goldSpeaker is null)
     # rewards the model for recognizing genuine ambiguity instead of confidently guessing wrong
```

**Calibration error (ECE — Expected Calibration Error):** bucket every scored row by predicted
confidence into `B` equal-width bins (`B=10`, i.e. deciles); for each bin `b` compute mean predicted
confidence `conf(b)` and empirical accuracy `acc(b)`; weight by bin population `n(b)` over total `N`:

```
ECE = sum over bins b of ( n(b) / N ) * | acc(b) - conf(b) |
```

Low ECE means "a reported 0.9 really is right ~90% of the time" — the property auto-accept
depends on (§4).

**Inter-annotator ceiling:** report `human_agreement_rate` (the fraction of `attribution-sample.json`
rows marked `agreement: unanimous`) alongside every accuracy number above, so a reviewer can see
whether the model is closing in on the practical ceiling or still has real room.

### 3.4 Direction — agreement / kappa vs. human labels

Direction fields are partly categorical (`emotion`, `tone`) and partly ordinal
(`intensity`, `pace`). Both are scored against `direction-sample.json`:

```
# Categorical (emotion): Cohen's kappa between model prediction and the majority/either-annotator
# gold label (a prediction counts correct if it matches ANY of the sample's recorded gold labels,
# per §2.2's multi-label allowance).
kappa = (p_o - p_e) / (1 - p_e)
  where p_o = observed agreement rate (model vs. gold-label-set)
        p_e = expected agreement rate by chance, computed from each label's marginal frequency

# Ordinal (intensity, pace-as-scalar): quadratic weighted kappa, which penalizes a prediction
# proportionally to how far off the ordinal scale it lands (mistaking "urgent" for "somber" is a
# bigger miss than mistaking "urgent" for "tense").
```

**Inter-annotator kappa** is computed the same way between the sample's own two-or-more annotators
and reported as the ceiling — per §2.2.2, a model is not faulted for falling short of a ceiling
that human annotators themselves did not clear (i.e., if annotators only agree at kappa 0.55 on a
genuinely subjective scene, the model is not held to a higher bar than 0.55 for that scene).

### 3.5 Casting — constraint-violation count, distinctiveness score

Both reused directly from
[automatic-casting-v2.md §Quality evaluation](../casting/automatic-casting-v2.md#quality-evaluation),
computed over a fixed benchmark project's casting run (any book from §2.1 with its characters run
through the real auto-casting algorithm):

```
hard_constraint_violations = count of assigned (character, voice) pairs where
                              voice.facet(k) not in (required[k], "unknown") for any required facet k
     # target: always 0 — a nonzero count is a solver bug, not a quality tradeoff (facet_match
     # returns -INF for these; see automatic-casting-v2.md Step 2)

avoidable_major_collisions = count of scenes where two MAJOR characters share a voice AND an
                             unused, hard-constraint-satisfying voice existed at assignment time
     # target: trending to 0; a nonzero count with NO unused valid voice is honest degradation
     # (catalog too small), not a defect — see automatic-casting-v2.md's consistency-rules table

distinctiveness_score(pair) = 1 - cosine_similarity(voice_a.embedding, voice_b.embedding)
     # (falls back to normalized pitch-median distance when no embedding model is installed,
     # per automatic-casting-v2.md's voice catalog "degrade gracefully" note)

project_min_pairwise_distinctiveness = min over all scene_co_occurrence pairs of distinctiveness_score(pair)
pct_pairs_below_threshold = (conversational pairs with distinctiveness_score < DISTINCT_THRESHOLD)
                             / (total conversational pairs)
```

`DISTINCT_THRESHOLD` is calibrated at the TTS bake-off (§7), not assumed — see
[automatic-casting-v2.md](../casting/automatic-casting-v2.md#step-2--scoring-scorevoice-character-already_assigned).

### 3.6 Audio QA — LUFS/TP/silence/clipping + ASR word-error alignment

**These are not new metrics.** They are the exact, already-implemented functions in
`apps/api/src/echodraft_api/audio_analysis.py` and the ASR hook described in
[qa-rulebook.md](qa-rulebook.md#implemented-phase-2-task-b2g11-echodraft_apiaudio_analysis) and
[qa-rulebook.md's linguistic checks](qa-rulebook.md#automated-linguistic-checks):
`peak_dbfs`/`clipped_sample_count > 8` (clipping), dead-air/silence run detection, whole-file RMS
loudness bounds, chapter integrated-loudness vs. **−19 LUFS ±1**, true peak vs. **−3 dBTP**, and
ASR normalized word-match ratio vs. **0.90**. What this harness adds is not a new formula but a new
*application*: run the identical functions against every rendered golden-corpus segment/chapter on
every eval run, and track the resulting numbers as a **time series across code changes** (§5.4,
§6) — the runtime layer only ever sees one point in time on one project; this harness is the only
place a regression ("clipping rate crept up after the mixer refactor") is even visible.

### 3.7 Sound design — guardrail violations, level compliance

Reused directly from
[generative-sound-design.md's taste guardrails](../assembly/generative-sound-design.md#taste-guardrails-machine-checked)
and [§Evaluation plan](../assembly/generative-sound-design.md#evaluation-plan):

```
guardrail_violations = count of: cues exceeding their mode's gain ceiling (light_cinematic:
  ambience/music <= -18dB, SFX <= -14dB; dramatized: <= -14dB / <= -10dB) +
  SFX events overlapping an active music window +
  chapters exceeding their configured SFX budget +
  speech_only chapters with any generated cue at all
     # target: always 0 — these are enforced in code (the planner/mixer clamp); a nonzero count
     # is a regression in the enforcement itself, not a taste judgment call.

level_compliance_pct = (generated/bank assets within +/-1 LUFS of the -23 LUFS pre-normalization
                         reference) / (total assets)
tonal_artifact_rate = (assets flagged by the spectral-flatness check) / (total generated assets)
```

### 3.8 Performance — wall-clock, RTF, UI main-thread budgets

```
stage_wall_clock_seconds(stage, book) = measured elapsed time for one stage on one golden-corpus
                                         book, at a fixed worker-pool size P (report P alongside
                                         the number — it is not comparable across P values)

RTF(engine) = synthesis_wall_time_seconds / rendered_audio_duration_seconds
     # measured warm (model already loaded in the engine host, per tts-engine-strategy.md §10)

longtask_count_over_50ms, longtask_max_ms = from a PerformanceObserver({entryTypes: ["longtask"]})
     # session during a scripted interaction on the synthetic UI fixture (§2.4 Mode A),
     # per frontend-architecture.md's Performance Verification spec (reused verbatim)
```

## 4. Calibration procedures

This is the mechanism that makes "flags are rare and meaningful" (the confidence & flag model in
[extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#confidence--flag-model))
a reproducible number instead of a guess. It applies to every stage that emits a confidence score
consumed by the three-tier auto-accept policy: attribution (S4), cast reconciliation (S3), and
direction (S5).

### Step-by-step procedure

1. **Run the stage in diagnostic mode against the golden corpus.** `uv run echodraft-eval --suite
   attribution --book <slug> --calibrate` runs the stage exactly as production would, but against
   the labeled fixture, and additionally joins every prediction to its gold label, emitting one row
   per decision: `{predictedLabel, rawConfidence, correct: bool, goldAmbiguous: bool}`. Do this
   across **all five books** — calibration fit on one book's prose style does not transfer reliably
   (§10 risks).
2. **Build the reliability diagram.** Bucket rows by `rawConfidence` into deciles; plot/store
   `(mean predicted confidence, empirical accuracy)` per bucket — this is the same computation as
   the ECE formula in §3.3, kept as an artifact (`reliability_diagram.json` + a rendered PNG/SVG in
   the run's report directory, §5.4) so a human can visually sanity-check the curve, not just read
   one scalar.
3. **Fit a calibration mapping.** Use **isotonic regression** (a monotonic, nonparametric fit),
   not Platt scaling — the only property needed is that a higher raw confidence never maps to a
   lower calibrated confidence, and isotonic regression does not assume a sigmoid shape the raw
   scores may not have. The fitted mapping is a piecewise-constant lookup table:
   `calibrated_confidence = isotonic_fit(raw_confidence)`.
4. **Choose `HIGH`** as the lowest calibrated confidence value for which
   `auto_accept_precision(rows with calibrated_confidence >= HIGH) >= target` (target = 0.95 for
   attribution, per [extraction-pipeline-v2.md's goals table](../../architecture/extraction-pipeline-v2.md#goals-explicit-budgets);
   see §6 for the per-stage target table). Search the calibrated-confidence grid from `1.0` downward
   and stop at the first value satisfying the constraint.
5. **Choose `MID`** as the lowest calibrated confidence such that the resulting flag volume
   (rows below `MID` **after** voting/reduce) stays under the per-book budget (`< 20 tasks/book`
   aggregate across all flag sources — §6) **while** flag precision (a flagged row really is
   ambiguous, i.e. `goldAmbiguous: true` or a genuine model/human disagreement) stays `>= 0.8`.
   These two constraints can conflict; when they do, flag-volume is the harder constraint (the
   product mandate is zero-touch first) and flag-precision below `0.8` is logged as an open
   calibration risk rather than silently accepted.
6. **Persist the fit.** Write the isotonic mapping and the chosen `HIGH`/`MID` to a versioned file:
   `apps/api/src/echodraft_api/eval/calibration/{stage}-{modelId}-{schemaVersion}.json`, e.g.
   `attribution-qwen3_4b_ollama-attribution-v2.json`. The running pipeline stage loads this file
   instead of a hardcoded constant — calibration output *is* the production configuration, not a
   report that a human manually transcribes into code.
7. **A threshold change is itself a change that must pass the harness.** Recalibrating and shipping
   a new `HIGH`/`MID` requires re-running §6's gates with the new thresholds and diffing them
   against the previous file (`git diff` on the calibration JSON is a legitimate, reviewable code
   change) before merge — never auto-promoted.

```json
{
  "stage": "attribution",
  "modelId": "qwen3_4b_ollama",
  "schemaVersion": "attribution-v2",
  "fittedAt": "2026-07-07T00:00:00Z",
  "corpusBooks": ["pride-and-prejudice", "sherlock-holmes", "the-time-machine", "earnest", "modern-format-synthetic"],
  "isotonicMapping": [[0.0, 0.02], [0.1, 0.11], ["...": "..."], [1.0, 0.99]],
  "thresholds": {"HIGH": 0.93, "MID": 0.62},
  "measuredAt": {"autoAcceptPrecision": 0.956, "flagVolumePer100pp": 3.1, "flagPrecision": 0.84, "ece": 0.031}
}
```

### Recalibration triggers

Recalibration (steps 1–7) is required, not optional, whenever:

- the backing model changes (`modelId` or its version — e.g. an Ollama model bump, a Tier-S TTS
  engine swap per §8);
- the stage's output schema version changes (e.g. `attribution-v2` → `attribution-v3`);
- the golden corpus itself changes (a book added, a label file corrected);
- a scheduled quarterly drift check, even absent any known change, to catch silent environment
  drift (library version bumps affecting numeric feature extraction, etc.).

A stale calibration file (loaded by a pipeline whose `modelId`/`schemaVersion` no longer matches
the file's own recorded values) is a **hard startup warning**, not a silent fallback — the
pipeline should refuse to claim a calibrated `HIGH`/`MID` it cannot prove still applies.

## 5. Harness architecture

### 5.1 The `eval` runner

A new console script, `echodraft-eval`, added the same way `echodraft-api` is today (`apps/api/pyproject.toml`'s `[project.scripts]`):

```
uv run echodraft-eval --suite structure   --book pride-prejudice
uv run echodraft-eval --suite attribution --book sherlock-holmes --stage-input fixture
uv run echodraft-eval --suite cast        --book the-time-machine
uv run echodraft-eval --suite direction   --book earnest
uv run echodraft-eval --suite casting     --book pride-prejudice
uv run echodraft-eval --suite audio-qa    --book earnest
uv run echodraft-eval --suite sound-design --book pride-prejudice --tier tier0
uv run echodraft-eval --suite tts-bakeoff --engine chatterbox --scripts all
uv run echodraft-eval --suite performance --book synthetic-500pg --llm replay
uv run echodraft-eval --suite full        --corpus golden --mode replay      # CI fast subset
uv run echodraft-eval --suite full        --corpus golden --mode live        # nightly/pre-release
uv run echodraft-eval report --compare <run-id-a> <run-id-b>
```

Proposed module layout (new, under the existing `apps/api` package so it shares the container,
config, and repository code the real pipeline uses — an eval run exercises the *real* stage code,
never a reimplementation of it):

```
apps/api/src/echodraft_api/eval/
  cli.py             # argument parsing, suite dispatch — the echodraft-eval entry point
  runner.py          # stage-isolated execution (5.2), orchestrates one suite x one book
  fixtures.py        # loads golden-corpus labels + fixture-manifests from tests/fixtures/
  calibration.py     # reliability diagrams, isotonic fit, threshold search (§4)
  report.py          # JSON + markdown scorecard writer, baseline diff (5.4, 5.5)
  metrics/
    structure.py  cast.py  attribution.py  direction.py
    casting.py    audio_qa.py  sound_design.py  performance.py
apps/api/tests/eval/
  test_structure_metrics.py  test_calibration.py  test_report_format.py  ...
```

### 5.2 Stage-isolated evaluation

The manifest-driven design makes this natural: **a stage's evaluated input is a manifest, and its
evaluated output is a manifest**, exactly like production. To evaluate attribution (S4) in
isolation, the runner does not re-run ingestion/structure/cast first — it loads a **fixture
manifest**: a hand-corrected, gold-shaped `structure_manifest.json` + `casting_manifest.json`
committed under `tests/fixtures/golden-corpus/{slug}/fixture-manifests/`, feeds it directly to the
attribution stage's real entry point, and scores the stage's real output against
`attribution-sample.json`.

A fixture manifest is the same common envelope every manifest already uses
([pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md#common-envelope)), plus
one additive `fixture` block that records its provenance:

```json
{
  "manifestType": "structure_manifest",
  "schemaVersion": "structure-v2",
  "projectId": "eval_pride-and-prejudice",
  "generatedAt": "2026-06-01T00:00:00Z",
  "generator": {"service": "golden-corpus", "version": "1.0.0"},
  "status": "completed",
  "payload": { "chapters": ["..."], "segments": ["..."] },
  "diagnostics": [],
  "fixture": {
    "bookSlug": "pride-and-prejudice",
    "fixtureManifestVersion": "1.0.0",
    "derivedFromLabelVersion": "1.0.0",
    "sourceStageSchemaVersion": "structure-v2",
    "handCorrected": true
  }
}
```

Running a stage against a fixture manifest instead of a freshly-computed upstream manifest has two
benefits beyond isolation: it makes an attribution-only eval run fast (no structure/cast LLM calls
needed) and it keeps attribution's score stable even while structure v2 is still being built (§10
— attribution eval must have a baseline *before* pipeline v2 lands, which means it must be able to
run against a hand-built fixture manifest standing in for a structure stage that does not fully
exist yet).

### 5.3 Report output

Every run writes both a machine-readable and a human-readable artifact under a dated directory,
alongside the other filesystem-only runtime state Echodraft already keeps under `.echodraft/`
(never audio-in-DB, never eval-results-in-DB — paths only, consistent with constraint 7):

```
.echodraft/eval-runs/{YYYYMMDD-HHMMSS}-{suite}-{book}/
  report.json          # full machine-readable result: every scored row, every metric, config used
  scorecard.md          # human-readable summary: pass/fail per gate, deltas vs. baseline
  reliability_diagram.json + .png   # only for --calibrate runs (§4)
  raw/                  # llm_runs artifacts, TTS renders, or other bulky per-row evidence
```

`report.json` shape (abbreviated):

```json
{
  "runId": "20260707-141200-attribution-pride-and-prejudice",
  "suite": "attribution",
  "book": "pride-and-prejudice",
  "mode": "live",
  "modelVersions": {"stageModel": "qwen3:4b", "schemaVersion": "attribution-v2"},
  "corpusVersion": {"labelVersion": "1.0.0", "fixtureManifestVersion": "1.0.0"},
  "metrics": {"accuracy": 0.968, "autoAcceptPrecision": 0.956, "recallAttributableDialogue": 0.941, "ece": 0.031},
  "gateResults": [{"metric": "autoAcceptPrecision", "threshold": 0.95, "level": "hard", "value": 0.956, "pass": true}],
  "rows": ["... one entry per scored attribution row, with predicted/gold/confidence ..."],
  "startedAt": "2026-07-07T14:12:00Z", "finishedAt": "2026-07-07T14:19:41Z"
}
```

`scorecard.md` is a short generated table (metric, threshold, value, pass/fail, delta vs. the
compared baseline) meant to be pasted into a PR description or read at a glance — not a
restatement of `report.json`'s row-level detail.

### 5.4 Comparison vs. baseline

`uv run echodraft-eval report --compare <run-id-a> <run-id-b>` diffs two `report.json` files
metric-by-metric and reprints §6's gate table with a `delta` column. For everyday use, a pointer
file avoids having to know the exact previous run id:

```
.echodraft/eval-runs/baseline-pointer.json
  { "structure/pride-and-prejudice": "20260701-090000-structure-pride-and-prejudice", "...": "..." }
```

`uv run echodraft-eval --suite structure --book pride-prejudice --compare-baseline` reads this
pointer, runs the new eval, and reports the delta automatically. The pointer only advances when a
human explicitly promotes a run (`echodraft-eval baseline set <run-id>`) — never automatically on
a passing run, so "the baseline" is always a deliberate, reviewable choice (this mirrors the
model-update protocol's promotion gate in §8).

## 6. Regression gates

All gates run **locally** — no cloud dependency, per constraint 4. "Hard" blocks merge; "soft"
surfaces in the scorecard and must be acknowledged in review but does not fail CI by itself.

| Suite | Metric | Threshold | Level | Cadence |
|---|---|---|---|---|
| Structure | coverage-invariant pass rate | `= 100%` | hard | PR fast subset + nightly |
| Structure | chapter boundary F1 | `>= prior baseline - 1pt` | hard | nightly full corpus |
| Structure | scene boundary F1 | `>= prior baseline - 1pt` | soft | nightly full corpus |
| Cast | roster precision | `>= 0.98` | hard | nightly full corpus |
| Cast | alias-cluster purity (V-measure) | `>= prior baseline (no regression)` | hard | nightly full corpus |
| Cast | merge/split error rate | `<= prior baseline` | soft | nightly full corpus |
| Attribution | auto-accept precision | `>= 0.95` | hard | PR fast subset (replay) + nightly (live) |
| Attribution | recall of attributable dialogue | `>= 0.90` | hard | nightly full corpus |
| Attribution | calibration error (ECE) | `<= 0.05` | hard | nightly (recalibration runs, §4) |
| Attribution | headline accuracy (product target) | `>= 0.98` | soft | nightly full corpus — tracks [product-vision-v2.md §5.3](../../product/product-vision-v2.md#53-attribution--casting-accuracy) directly |
| Flags | flags per 100 pages | `<= 4` | hard | nightly full corpus |
| Flags | flag precision | `>= 0.8` | soft | nightly full corpus |
| Direction | kappa vs. human labels | `>= 0.6` (below the human-human ceiling per scene, §3.4) | soft | nightly, `earnest` + one prose book |
| Casting | hard-constraint violations | `= 0` | hard | PR fast subset (deterministic, no model needed) |
| Casting | avoidable major-voice collisions | `<= prior baseline` | soft | nightly |
| Casting | project min pairwise distinctiveness | `>= DISTINCT_THRESHOLD` (§7 bake-off) | soft until calibrated, then hard | nightly |
| Audio QA | clipping / dead-air / loudness / ASR-WER | existing [qa-rulebook.md](qa-rulebook.md) thresholds, applied to golden-corpus renders | hard | nightly (requires TTS render) |
| Sound design | guardrail violations | `= 0` | hard | PR fast subset (Tier 0, no model needed) |
| Sound design | tonal-artifact rate | `<= prior baseline` | soft | nightly (Tier 1+ only) |
| Performance | per-stage wall-clock at fixed `P` | within the budget band in [extraction-pipeline-v2.md §Goals](../../architecture/extraction-pipeline-v2.md#goals-explicit-budgets) | hard | nightly (`--llm live`) |
| Performance | orchestration overhead (`--llm replay`) | `<= prior baseline` | soft | PR fast subset |
| Performance | TTS RTF (warm) | `< 1.0` per tier's target device | hard | nightly, gates Tier-S promotion (§8) |
| UI performance | longtask count `> 50ms` during scripted interaction | `= 0` | hard | PR fast subset ([frontend-architecture.md](../../ui/frontend-architecture.md#performance-verification)'s existing Playwright spec) |
| UI performance | bundle size per route | per-route budget table in frontend-architecture.md | hard once 2 green weeks established, else soft | PR fast subset |

### How gates run

- **PR fast subset (every pull request touching pipeline/eval/frontend-perf code):** a reduced
  sample (1–2 chapters per book, or the whole `modern-format-synthetic` fixture since it is small)
  with LLM/TTS calls served from a pre-populated replay cache — deterministic, no model install
  needed, runs on the same `ubuntu-latest` runner as the existing `backend`/`web`/`smoke` jobs in
  `.github/workflows/ci.yml`. This mirrors the "LLM either live (nightly) or replayed from cached
  fixtures (CI, deterministic)" split already specified in
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#quality-evaluation-harness).
- **Full corpus, nightly/pre-release:** the entire five-book golden corpus, live models
  (`--mode live`), run on a developer machine with Ollama (and, for TTS/sound-design bake-off gates,
  optionally a GPU) — never on shared CI infrastructure, since local LLM/TTS inference at this scale
  needs hardware CI runners don't have. §9 draws this line precisely.

### What happens on regression

- **Hard gate regression:** the PR/local check fails; merge is blocked. The fix is either a code
  fix (the common case) or a deliberate, reviewed recalibration (§4 step 7) that moves the
  threshold/baseline forward with an explicit rationale in the PR description — never a silent
  baseline bump to make a failing run pass.
- **Soft gate regression:** the scorecard shows the regression and the PR reviewer must
  acknowledge it explicitly (a written note, not a rubber stamp) before merge; it does not block
  automatically. Three consecutive acknowledged soft regressions on the same metric is a signal to
  promote that metric to a hard gate.
- **Every regression, hard or soft, is recorded** in the run's `report.json` — there is no
  "regression happened but nobody can find evidence of it later" state, matching the "durable
  diagnostic evidence, never discarded" principle used everywhere else in this codebase.

## 7. Listening evaluation (the human layer)

Some quality claims — does this sound angry, does this ambience distract, does this voice sound
like a different person than that voice — cannot be fully certified by a waveform measurement.
This section is the **one** structured instrument for all of them, consolidating the bake-off
rubric from [tts-engine-strategy.md §10](../tts/tts-engine-strategy.md#10-bake-off-protocol-evidence-based-selection),
the blind-panel checklist from
[automatic-casting-v2.md](../casting/automatic-casting-v2.md#quality-evaluation), and the human
evaluation panel from
[generative-sound-design.md §Evaluation plan](../assembly/generative-sound-design.md#evaluation-plan)
into one reusable protocol, rather than three slightly different ad-hoc rubrics.

This is distinct from, and does not replace, [qa-rulebook.md's human editorial/listening
checklists](qa-rulebook.md#human-editorial-checklist) — those are the **per-project, production-time**
checklists a real user or reviewer applies to their own book before approving a chapter. This
protocol is the **model/version-comparison** instrument used when deciding whether a new engine,
model, or tuning change is actually better, using the same fixed corpus every time so results are
comparable across sessions.

### 7.1 The general rubric (1–5 scale unless noted)

| Axis | Question | Used for |
|---|---|---|
| Naturalness | Does this sound like a real speaker, not a synthesis demo? | TTS bake-off, model-update protocol |
| Expressiveness / emotion fidelity | Does the directed emotion (angry/whispered/grieving/…) actually come through? | TTS bake-off, model-update protocol |
| Consistency | Same timbre/loudness/accent across the sample — no drift? | TTS bake-off, long-form quality regression |
| Artifacts | Binary yes/no + timestamp: any click, seam, tonal drone, hallucinated word/voice/melody? | TTS bake-off, sound-design panel |
| Distinctiveness | Can you tell who's speaking without the transcript, for every major-character pair? | Casting blind A/B |
| Appropriateness / restraint | Does ambience/music fit the scene and stay out of the way of the words? | Sound-design panel |
| Presence | "Would you notice if this cue were silently removed?" (target: "barely," not "no" or "very much") | Sound-design panel |
| Overall immersion | Same 7-point checklist as [qa-rulebook.md's human listening rubric](qa-rulebook.md#human-listening-rubric) | Cross-check against production-time rubric |

A session picks the subset of axes relevant to what it's comparing (a TTS bake-off session doesn't
score "Presence"; a sound-design session doesn't score "Naturalness") but always uses this same
table's wording and scale, so scores are comparable across sessions run months apart.

### 7.2 Blind A/B session design

1. **Fixed corpus, fixed scripts.** Use the same test scripts every time a given comparison type
   runs: the eight TTS scripts in
   [tts-engine-strategy.md §10](../tts/tts-engine-strategy.md#10-bake-off-protocol-evidence-based-selection)
   for engine comparisons; a fixed multi-character scene from the golden corpus for casting
   distinctiveness; the fixed regression corpus of representative chapters for sound-design panels.
2. **Blind labeling.** Conditions (engine A vs. B, Tier-0 vs. Tier-1 ambience, old vs. new model
   version) are assigned opaque labels (`condition_1`, `condition_2`) before the session; the
   mapping is revealed only after all scores are recorded.
3. **Counterbalanced order.** Half the reviewers hear condition 1 first, half hear condition 2
   first, to cancel out ordering/fatigue bias.
4. **Independent scoring, then aggregate.** Each reviewer scores every item alone before any
   discussion; only after independent scores are recorded does the session optionally add a
   free-text discussion note.

### 7.3 Sample-size guidance

Likert-style 1–5 scores from a handful of raters are noisy; treat results directionally below the
following floors, and do not promote an engine/model/tier based on an under-sampled session:

| Decision being made | Minimum raters | Minimum items per condition |
|---|---|---|
| Promote a Tier-S TTS engine from experimental to default | 3 | all 8 bake-off scripts |
| Promote a sound-design tier (Tier 3 → Tier 1/2) | 3 | the full regression corpus (§ generative-sound-design.md) |
| Spot-check regression between two builds of the *same* already-shipped engine | 2 | 3–5 representative clips |
| Casting distinctiveness spot-check | 1 (informal) | the fixed multi-character scene |

A small team means the same 1–2 people often rate everything — a real, acknowledged limitation
(§10 risks), mitigated by blinding and counterbalancing but not eliminated by them.

### 7.4 Session artifact format

Every session is a durable JSON file, not a chat log or a spreadsheet that evaporates:

```json
{
  "sessionId": "20260710-tts-bakeoff-chatterbox-vs-orpheus",
  "date": "2026-07-10",
  "type": "tts_bakeoff",
  "reviewers": ["rev_a", "rev_b", "rev_c"],
  "conditions": {"condition_1": "chatterbox", "condition_2": "orpheus-3b"},
  "revealedAfter": true,
  "items": [
    {"script": "angry_outburst", "reviewer": "rev_a", "condition": "condition_1",
     "scores": {"naturalness": 4, "expressiveness": 5, "artifacts": "none"}}
  ],
  "aggregate": {"condition_1": {"naturalness": {"mean": 4.1, "median": 4}}, "condition_2": {"...": "..."}},
  "decision": "promote condition_1 (chatterbox) to Tier S default",
  "notes": "condition_2 rambled on script 6 (long-paragraph stability) — see raw/condition_2_script6.wav"
}
```

Stored at `.echodraft/eval-runs/listening-sessions/{date}-{topic}/session.json`, alongside a
generated `summary.md` — the same directory convention as automated runs (§5.3), so a listening
decision is exactly as durable and auditable as an automated gate result.

## 8. Model-update protocol

Swapping the LLM tier, a TTS engine/model version, or a sound-design generative model requires
clearing this battery **before** the new version becomes the default:

1. **Run the full hard-gate table (§6) against the golden corpus with the new model**, in `--mode
   live`. Every hard gate the changed model touches must pass at parity with (not merely "close
   to") the current baseline — no regression is acceptable on a hard gate as the price of a model
   swap, even a swap expected to be an improvement elsewhere.
2. **Recalibrate (§4).** A model change invalidates the existing `HIGH`/`MID` calibration file for
   every stage that model backs — recalibration is not optional, it is a prerequisite step, since
   the old thresholds were fit against the old model's confidence distribution.
3. **Run the relevant listening battery (§7)** at the sample size in §7.3 for the kind of promotion
   being made (a Tier-S TTS engine swap needs the full 8-script panel; a sound-design model swap
   needs the full regression-corpus panel).
4. **Record an eval battery report** — a bundle referencing the full gate-table run and the
   listening session, diffed against the last promoted baseline — and require **explicit human
   sign-off** before `echodraft-eval baseline set` moves the pointer (§5.4). A model swap is never
   auto-promoted on green CI alone.
5. **Render-history compatibility.** Nothing about a model swap invalidates history: model/engine
   identity is already pinned into `render_identity()`/the `render_key`
   ([tts-engine-strategy.md §11](../tts/tts-engine-strategy.md#11-migration-path-risks-open-questions))
   and into each LLM call's `llmRunId`/model tier
   ([extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#model-tiering-tie-to-the-model-center-catalog)),
   so existing renders and existing manifests remain valid and reproducible under their originally
   recorded model version (append-only, constraint 6) — a swap only ever changes what *new* work
   uses. The eval harness applies the same discipline to itself: every `report.json` records
   `modelVersions` (§5.3) so a report read years later is still interpretable against what produced
   it, even after the default has moved on multiple times since.

## 9. Integration with the QA runtime and with CI

### The boundary with qa-rulebook.md / readiness-qa.md

| | Runtime QA ([qa-rulebook.md](qa-rulebook.md), [readiness-qa.md](readiness-qa.md)) | This harness |
|---|---|---|
| Runs against | a real user's real project | the golden corpus (known-truth fixtures) |
| Needs ground truth? | no — self-contained measurements (clipping, silence, loudness) or structural invariants | yes — every accuracy/precision/recall/kappa number requires a hand-labeled answer |
| Gates | that one project's chapter/export approval | a code change's merge (§6) |
| When it runs | on every render, every readiness report request, in the running app | on every PR (fast subset) and nightly/pre-release (full corpus), never inside the shipped app |
| Can it prove a threshold is right? | no — it only applies whatever threshold this harness (and calibration, §4) determined | yes — this is the only place a threshold like "WER match ratio 0.90" or "auto-accept HIGH = 0.93" is derived and validated |
| Shared code? | yes, deliberately — audio-technical checks (§3.6) are the literal same `audio_analysis.py` functions in both layers | same |

Concretely: `qa-rulebook.md`'s runtime checks are **not being replaced or duplicated**. This
document's audio-QA suite (§3.6) calls the exact same functions, on the same code path, against
different input (golden-corpus renders instead of a live user's renders) for a different purpose
(catch a regression across a code change instead of gate one export). Anywhere this document and
`qa-rulebook.md` state a numeric threshold, they must agree — `qa-rulebook.md` is the source of
truth for the threshold's current value, and §4's calibration procedure is how that value is
derived and updated over time.

### CI vs. developer machine

| Environment | What runs | Why |
|---|---|---|
| Repo CI (`ubuntu-latest`, no GPU, no Ollama) | PR fast subset (§6): replayed-LLM/TTS structure & attribution checks on a reduced sample, deterministic calibration-mapping unit tests, Tier-0 (procedural/CC0) sound-design automated gate, the frontend Playwright perf spec + bundle-size check, casting hard-constraint check (pure code, no model) | None of these need a live model or real audio synthesis — they test *code correctness* against fixed inputs, exactly like the existing `backend`/`web`/`migrations`/`smoke` jobs in `.github/workflows/ci.yml`, which this would join as a new `eval-fast` job (proposed, not yet added) |
| Developer machine with Ollama installed (+ optionally a GPU) | Full golden-corpus suite in `--mode live`: real structure/cast/attribution/direction LLM calls, TTS bake-off + RTF measurement, Stable Audio Open / Tier-1+ sound-design generation and its QA gate, the full nightly/pre-release gate table (§6) | Local LLM and generative-audio inference at golden-corpus scale needs real inference hardware and, for Tier-S TTS and Tier-1+ sound design, meaningfully benefits from a GPU that CI runners don't have — this is the same split [target-architecture.md](../../architecture/target-architecture.md) and [tts-engine-strategy.md](../tts/tts-engine-strategy.md) already draw between what CI can exercise and what needs real inference hardware |

The fast/replay CI tier catches *code* regressions (a refactor that breaks the coverage verifier,
a calibration-file loader bug, a mixer change that violates a gain ceiling) on every PR, cheaply.
It **cannot** catch a *model-quality* regression (a subtly worse prompt template that still
produces schema-valid, differently-wrong JSON) — that gap is real and is called out honestly in
§10 rather than papered over; closing it requires the nightly live run, which is why the nightly
tier is a **hard** requirement, not a nice-to-have.

## 10. Rollout plan, risks, and open questions

### Rollout order

1. **Attribution eval first — before extraction-pipeline-v2 lands.** Build the fetch script, label
   `pride-and-prejudice` and `sherlock-holmes` (the two highest-value books for attribution: dense
   ensemble dialogue and a hard narrator-vs-quoted-character case), the attribution metric (§3.3),
   and the minimal harness skeleton (CLI, report format, §5) — enough to run
   `uv run echodraft-eval --suite attribution --book pride-prejudice` against **today's v1**
   deterministic-cascade-plus-LLM-cleanup attribution code. This establishes the v1 baseline the v2
   redesign must beat, satisfying the explicit product requirement that the redesign have something
   concrete to measure against on day one.
2. **Structure + cast eval, plus the remaining three books**, once
   [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)'s S2/S3 land behind
   their feature flags (its own migration §Migration path step 1 already calls for landing "the
   eval harness with golden fixtures" as its first foundation step — this is that harness).
3. **Calibration procedure (§4) wired in** as soon as attribution v2 emits a real confidence score
   — this is what turns the three-tier flag model from a design intention into an enforced
   mechanism.
4. **Casting eval (§3.5)** once [automatic-casting-v2.md](../casting/automatic-casting-v2.md) lands.
5. **TTS bake-off harness (§7 general instrument + §8 protocol)** — independent of the pipeline
   accuracy work above, can be built in parallel; required before any Tier-S engine is promoted.
6. **Sound-design automated gate (§3.7), Tier 0 first** (needs no model, ships alongside Tier 0 per
   [generative-sound-design.md's own migration plan](../assembly/generative-sound-design.md#migration-path)),
   then the blind A/B panel once a Tier-1 model is integrated.
7. **Performance/UI harness (§2.4, §3.8)** — also independent, can start early since it only needs
   the seeding script and synthetic manuscript generator, not pipeline accuracy.
8. **`eval-fast` CI job** wired into `.github/workflows/ci.yml` once the replay-mode fast subset is
   stable enough not to be flaky — recommended `continue-on-error: true` for the first two weeks,
   mirroring the caution already recommended for the frontend perf job in
   [frontend-architecture.md](../../ui/frontend-architecture.md#ci-gates).

### Risks

- **Genre/style transfer.** Calibration fit on five specific public-domain books may not transfer
  to contemporary or genre fiction a real user drops in — the same open risk
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md#risks--open-questions)
  already flags, directly inherited here since this harness is what would have to detect it.
- **Replay CI cannot catch model-quality regressions**, only code regressions (§9) — a real,
  acknowledged blind spot that only the nightly live tier closes; a bad prompt-template change
  could ride through several green PRs before the nightly run catches it.
- **Direction/kappa ground truth is itself subjective.** Two careful annotators can legitimately
  disagree on whether a line is "tense" or "urgent" — §3.4's ceiling reporting mitigates this by
  never holding the model to a bar humans didn't clear, but establishing what kappa counts as
  "acceptable ground truth" before any model comparison is an open methodological question, not a
  solved one.
- **Small-team reviewer bias.** §7.3 already surfaces that a small team likely means 1–2 people
  rate most listening sessions repeatedly, risking anchoring across sessions — partial blinding
  mitigates, does not eliminate, this.
- **Label/fixture-manifest maintenance cost.** Fixture manifests are pinned to a `schemaVersion`
  (§5.2); a breaking schema change on a real pipeline manifest requires a corresponding fixture
  manifest migration, which is real, recurring work with no automation proposed here (unlike
  Alembic for the database) — currently a manual step to budget for, not a solved pipeline.
- **The harness itself must not become the next 6-hour bottleneck.** As the corpus and gate table
  grow, the nightly full-corpus run's own wall-clock needs a budget and should be measured by the
  same §3.8 performance discipline it applies to the product pipeline — a meta-risk worth taking
  seriously from the first build, not after the nightly run becomes unbearable.

### Open questions

- What is the right per-book weighting when aggregating a metric across all five golden-corpus
  books — equal weight per book, or weight by page count / segment count? This changes what "no
  regression" means whenever one book's numbers move against another's.
- Should `DISTINCT_THRESHOLD` (§3.5) and the TTS bake-off's numeric promotion bars (§6's
  "starting point" values) be corpus-wide constants, or tuned per hardware tier the way engine
  tiering itself is? Deferred to real bake-off data, consistent with every "verify at bake-off"
  caveat already threaded through [tts-engine-strategy.md](../tts/tts-engine-strategy.md).
- At what corpus size does labeling cost stop being worth the marginal calibration improvement —
  i.e., when (if ever) does the golden corpus grow past five books, and who decides?
- Should the fast/replay CI tier eventually get its own small, separate "replay corpus" distinct
  from a reduced slice of the golden corpus, to avoid the replay cache silently going stale against
  the live corpus's label updates? Not resolved here; worth revisiting once the replay tier exists
  and has been lived with for a while.
