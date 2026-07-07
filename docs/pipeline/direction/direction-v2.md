# Direction / Performance Inference v2

Direction is the pipeline's **performance script**: for every segment it decides
*how a line is delivered* — emotion, intensity, pace, pauses, nonverbals — before
any audio exists. This document specifies **direction inference v2**: how that
script is produced automatically, with zero user input, at a quality high enough
that an expressive engine has something genuinely worth performing.

This is the **input side** of expressive TTS. It does *not* specify how a
`DirectionProfile` becomes engine-native controls (tags, exaggeration knobs,
emotion vectors, acting-ref selection) — that compilation step is owned end to
end by [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md) §5
("Direction → engine contract v2"). The two documents meet at the
`DirectionProfile` schema (§3 here) and nowhere else.

See also: [`direction-studio.md`](direction-studio.md) (current v1 behavior this
doc replaces), [`../../architecture/extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
(§S5 sketches this stage inside the shared scene-window framework; this doc is
the full specification of that stage), [`../casting/automatic-casting-v2.md`](../casting/automatic-casting-v2.md)
(character speech-style profiles this doc consumes as delivery baselines),
[`../casting/voice-bible-spec.md`](../casting/voice-bible-spec.md) (`maxExpressiveness`,
`narrationRestraint`, `allowWhispering`/`allowShouting` — the project-level taste
caps this doc enforces), [`../assembly/generative-sound-design.md`](../assembly/generative-sound-design.md)
(consumes the scene emotional arc manifest, §5), [`../../architecture/pipeline-manifest-spec.md`](../../architecture/pipeline-manifest-spec.md)
(manifest envelope conventions), [`../../architecture/target-architecture.md`](../../architecture/target-architecture.md)
(job runner, checkpoint store, LLM worker pool this stage runs on), and the
parallel-track docs [`../../domain/domain-model-v2.md`](../../domain/domain-model-v2.md)
and [`../../api/api-v2-contracts.md`](../../api/api-v2-contracts.md), which should
incorporate the data-model and API deltas in §8.

## 1. Purpose, goals, non-goals

### Purpose

Today's pipeline infers a `DirectionProfile` per segment and then, per the
current TTS research, **throws almost all of it away** — no shipped engine
receives anything beyond `pace` and the pause fields
([`direction-studio.md`](direction-studio.md) "Engine Capability And What Is
Actually Honored"). That gap has two independent halves: (1) no engine can
*consume* rich direction yet, and (2) the direction that *is* produced today is
shallow, single-line keyword sniffing with no awareness of the scene it sits in.
[`tts-engine-strategy.md`](../tts/tts-engine-strategy.md) closes half (1). This
document closes half (2): it makes direction good enough, structured enough, and
cheap enough to produce that it is worth an engine's time to honor once that
engine exists. Shipping richer direction now — even before Tier-S engines land —
is not wasted work: it is stored, evidence-backed, and immediately renders
through the existing fallback ladder at whatever fidelity today's engines allow.

### The quality claim

**Direction quality is the difference between TTS that reads and TTS that
performs.** A narrator that speaks every line at the same pace and neutral tone
is unmistakably a machine; a narrator whose delivery tracks the scene's dramatic
shape — restrained in exposition, tightening through rising tension, breaking
for a beat before a reveal — is what separates an audiobook from a screen
reader. That shape cannot come from inspecting one line in isolation; it has to
come from understanding what the *scene* is doing.

### Goals

1. **Every segment carries calibrated direction, always.** No segment reaches
   chapter production with only the neutral default (direction-studio's
   resolution order, item 4) unless the manuscript genuinely gives no signal —
   zero-touch is the default path, not an opt-in job a user has to remember to run.
2. **Direction is grounded in narrative context, not per-line keyword matching.**
   A line's delivery is derived from what is dramatically happening in its scene
   (§4), not from whether the word "rain" appears in it (§2).
3. **Zero-touch by default, user-overridable always.** Auto-inference runs
   automatically after speaker attribution stabilizes (mirroring cast
   discovery's auto-chain, [`character-bible.md`](../casting/character-bible.md));
   every decision remains editable, lockable, and reversible (§7).
4. **Consistency within a scene.** Adjacent lines from the same emotional beat
   must not whiplash between unrelated emotions merely because a keyword
   fired differently (§4, consistency smoothing).
5. **Every decision is evidence-backed and reviewable**, and review only
   surfaces when the model is genuinely uncertain — direction should almost
   never produce a user-facing flag (§4, confidence & flags), consistent with
   [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
   three-tier policy.
6. **Fits inside the extraction wall-clock budget.** Direction is one of five
   stages sharing [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
   30–45 minute mid-tier target for a 500-page book, not a separate multi-hour
   pass a user waits through afterward (§8).
7. **Conservative by construction where it matters.** Narration stays
   restrained even when dialogue in the same scene is intense (§4), matching
   constraint 5 (conservative, tasteful audio production) and the voice
   bible's `narrationRestraint` default of `high`.

### Non-goals

- **Engine-side compilation.** Turning `emotion`/`intensity`/nonverbal markers
  into an engine's native control surface (tags, exaggeration scalars, emotion
  vectors, acting-ref selection) is entirely out of scope here — see
  [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md) §5. This document
  produces the contract's *input*; that document produces the contract's
  *output*.
- **Voice/timbre selection.** *Which* voice speaks is
  [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md)'s job. This
  document only reads that stage's character speech-style profiles as a
  delivery-baseline input (§3.5).
- **Ambience, music, and SFX placement.** Owned by
  [`generative-sound-design.md`](../assembly/generative-sound-design.md). This
  document only emits the scene emotional arc manifest (§5) that stage consumes
  for music placement; it does not place cues itself.
- **Re-specifying the job runner, checkpoint store, or LLM worker pool.**
  Owned by [`target-architecture.md`](../../architecture/target-architecture.md);
  this stage is a consumer of that infrastructure, identically to S3/S4 in
  [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md).
- **Perfect emotional interpretation.** The bar is *audiobook-production-good* —
  a reasonable, consistent, evidence-backed reading — not a literary critic's
  definitive interpretation of the text.

## 2. Current-state analysis (v1) — and its honest problem

`apps/api/src/echodraft_api/direction.py` implements today's pipeline:

**Deterministic heuristic (`DirectionService._infer`, always runs).** A single
`casefold()` scan of the segment text against a small, ordered set of keyword
buckets, first match wins:

```python
if any(token in text for token in ("whisper", "softly", "hushed")):
    emotion = "quiet"; whisper = True
elif "!" in segment.text_content or any(token in text for token in ("run", "hurry", "now")):
    emotion = "urgent"
elif "?" in segment.text_content:
    emotion = "tense"
elif any(token in text for token in ("grief", "alone", "rain", "grave")):
    emotion = "somber"
```

This is noisy by construction, and the noise is not hypothetical:

- `"rain"` triggers `somber` whether the sentence is *"Grief soaked through him
  like rain"* or *"They danced laughing in the warm summer rain"* — the keyword
  has no access to whether rain is elegiac or joyful in context.
- Any question mark makes a line `tense`, including *"Tea or coffee?"* asked by
  a cheerful host.
- Any exclamation mark or the word `"now"` makes a line `urgent`, including
  *"Come see this now, it's beautiful!"*
- The buckets are evaluated as an `if/elif` chain, so a line that is genuinely
  both urgent *and* touches a somber keyword only ever gets the first match —
  order, not content, decides.

**Optional LLM window refinement (`_apply_local_llm`, opt-in via
`useLocalLlm: true`).** Same-scene windows bounded by
`DIRECTION_INFERENCE_BATCH_CHARS=5000` / `DIRECTION_INFERENCE_BATCH_SEGMENTS=20`
(`_direction_context_windows`), marking segments `TARGET` vs `CONTEXT` exactly
like the v1 attribution prompt. This is a real improvement over the keyword
scan — it gives the model neighboring lines, the parser's speaker candidate, the
approved speaker attribution, and the deterministic direction as a hint — but it
inherits the same structural problem every v1 LLM pass has
([`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
"Failure analysis of v1"): **it runs windows strictly in series**, one blocking
Ollama call at a time, with no caching, no checkpointing, and no scene-level
narrative reasoning above the window. It also only *derives* a line's delivery
from nearby lines' *text* — it never asks "what is happening dramatically in
this scene," so a genuinely dramatic turn (a quiet scene suddenly interrupted)
gets no more narrative weight than an incidental line.

**Controlled vocabulary (`CONTROLLED_EMOTIONS`, 9 values).**
`neutral, warm, tense, quiet, urgent, somber, bright, fearful, angry` — a small,
schema-enforced enum (`_normalized` raises `ValueError` outside it). This
discipline is worth keeping; §3 extends it rather than replacing it.

**Resolution order** (unchanged by this document, restated for reference):
segment production override → `SegmentDirection` row → project
`default_direction` → neutral segment default
([`direction-studio.md`](direction-studio.md) "Production Resolution"). The
resolved payload feeds the segment render fingerprint, so a direction change
stales only that segment's cached renders.

**The honest problem, stated plainly.** Per the TTS research (see
[`tts-engine-strategy.md`](../tts/tts-engine-strategy.md) §1): `DirectionProfile`
already carries `pace`, `intensity`, `tone`, `emotion`, `pauses`,
`style_prompt`, `emphasis`, and `whisper`, and it is LLM-inferred — but **no
shipped engine receives anything beyond pace and pauses.** Everything else is
metadata that round-trips into `unsupportedDirection` and is never heard.
Improving inference quality without a consuming engine does not by itself fix
user-audible output; it is a necessary but not sufficient half of the fix (see
§10, "sequencing risk").

## 3. Direction schema v2

`DirectionProfile` v2 is **strictly additive** over v1
(`libs/domain-models/src/echodraft_domain/models.py:500`): every v1 field keeps
its name, alias, type, and bounds; every new field is optional with a default
that reproduces v1 behavior exactly. A v1 payload parses unchanged under the v2
model; a v2 payload with only v1 fields populated behaves identically to a v1
payload. No data migration or backfill is required for existing
`segment_directions` rows (§6, §10).

### 3.1 Expanded controlled emotion vocabulary (tiered)

v1's 9-value enum stays intact and gains 8 more values, chosen to (a) cover
gaps the product mandate calls out explicitly (anguish, laughter) and (b)
deliberately **share vocabulary with `generative-sound-design.md`'s scene
`mood` enum** (`neutral, warm, tense, quiet, urgent, somber, bright, fearful,
angry, calm, joyful, romantic, eerie, action`), so a scene's ambience mood and
its dialogue's delivery emotion stay coherent for the same moment without a
lookup table between them.

| Emotion | New in v2? | Definition |
|---|---|---|
| `neutral` | v1 | No strong affect; default. |
| `warm` | v1 | Affectionate, gentle, reassuring. |
| `bright` | v1 | Upbeat, energetic, light. |
| `tense` | v1 | Guarded, wary, anticipating conflict. |
| `urgent` | v1 | Time pressure, needs immediate action. |
| `somber` | v1 | Heavy, muted sadness — kept for restrained grief. |
| `fearful` | v1 | Afraid, threatened. |
| `angry` | v1 | Confrontational, hostile. |
| `quiet` | v1 | Low-energy, hushed (distinct from `warm`; often paired with `whisper`). |
| `grief` | v2 | Acute anguish/mourning — sharper than `somber`; the mandate's "anguish" case. |
| `joyful` | v2 | Unguarded happiness, laughter-adjacent. |
| `eerie` | v2 | Unsettling, uncanny, dread without explicit fear. |
| `romantic` | v2 | Intimate, tender, charged. |
| `calm` | v2 | Settled, at ease — distinct from `neutral` (affectively positive, not absence of affect). |
| `amused` | v2 | Wry, entertained, dry humor. |
| `defiant` | v2 | Resolute refusal, standing ground. |
| `contemptuous` | v2 | Scornful, dismissive. |

`emotion` remains the single required categorical field (backward compatible);
`intensity` (`0.0`–`1.0`, unchanged bounds) still scales magnitude within that
emotion.

### 3.2 Delivery modifiers (layered on top of emotion)

New field `deliveryModifiers: string[]`, drawn from a closed vocabulary,
representing *how* the emotion is being voiced rather than *what* it is. An
emotion and a modifier compose (`angry` + `trembling` reads very differently
from `angry` + `shout`):

| Modifier | Meaning | Mutual exclusions (§6) |
|---|---|---|
| `whisper` | Breathy, low-energy, near-silent | excludes `shout` |
| `shout` | Raised-voice, projected | excludes `whisper`, capped on `narration` (§4.3) |
| `trembling` | Voice shaking, barely controlled | pairs naturally with `fearful`/`grief` |
| `laughing` | Laughter breaking through speech | pairs with `joyful`/`amused` |
| `crying` | Voice breaking with tears | pairs with `grief`/`somber` |
| `sarcastic` | Ironic, meaning inverted from literal words | pairs with `amused`/`contemptuous` |
| `breathless` | Winded, short of breath | pairs with `urgent`/`fearful` |
| `flat` | Deliberately affectless (shock, deadpan) | excludes all others |

`whisper` remains a top-level boolean too (v1 compatibility: `DirectionProfile.whisper`
stays the source of truth for the existing whisper contract); v2 additionally
allows `"whisper"` inside `deliveryModifiers` for engines/tools that read the
list uniformly. The normalizer keeps both in sync (setting one sets the other).

### 3.3 Nonverbal event markers — inline span annotations, not markup

Nonverbals (laugh, sigh, gasp, sob, breath, a dramatic pause-beat) must **never**
be encoded as markup inside canonical segment text — canonical text is
immutable source-of-truth for the segment-first/patchability constraints, and
downstream stages (ASR validation, re-attribution, exports) must see the
manuscript's actual words. Instead, exactly like
[`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md) S2's
rule that the structural parser "returns offsets and labels only — never
manuscript text," nonverbal events are **character-offset spans stored on the
`SegmentDirection` row**, referencing the segment's own `text_content`:

```json
{
  "type": "laugh",
  "charStart": 42,
  "charEnd": 54,
  "confidence": 0.88,
  "evidenceQuote": "she laughed"
}
```

Rules:
- `[charStart, charEnd)` is a half-open, 0-based offset range into
  *that segment's* `text_content` — never into chapter/scene/canonical text, so
  a span survives any structural renumbering upstream unaffected.
- `evidenceQuote` must be a verbatim substring of `text_content[charStart:charEnd]`
  — a hard, machine-checkable invariant (§6), mirroring
  `generative-sound-design.md`'s `sentenceEvidence` discipline for SFX events.
- A marker is only ever emitted where the text *itself* signals it (a dialogue
  tag "laughed," an authored `*sigh*`, an onomatopoeia) — **never invented from
  `emotion` alone.** This is the same evidence-gated rule
  [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md) §5.2 applies at tag
  injection; direction v2 enforces it one layer upstream so a false nonverbal
  never even reaches the engine contract.
- Closed `type` vocabulary: `laugh, chuckle, sigh, gasp, sob, groan, breath, pause_beat`.
  `pause_beat` is the one type with no source-text span requirement (it marks a
  dramatic beat the narrative context implies, e.g. before a reveal) and instead
  carries a `charStart == charEnd` insertion point plus a suggested `pauseMs`.

### 3.4 Speaker-state continuity fields

Two fields carried *across a scene*, snapshotting cumulative state at the point
a segment occurs, so a character's fortieth line of a chase reads differently
from their first:

```json
"speakerState": {
  "agitation": 0.62,
  "fatigue": 0.30,
  "asOfSegmentId": "seg_1187"
}
```

- `agitation` (`0.0`–`1.0`): short-memory, decays across quiet lines and
  accumulates across tense/urgent/angry ones for that speaker within the scene.
- `fatigue` (`0.0`–`1.0`): longer-memory, rises across a scene of sustained
  exertion (a fight, a chase, a long grief scene) and resets at a scene
  boundary or an explicit rest beat.
- These are **context for the inference pipeline, not a user-facing control
  surface** — they are computed by Pass 2 (§4.2) from the beat sequence and
  stored for evidence/debugging and for the engine-side `stylePrompt` composer,
  not edited directly. A user overriding a segment's `emotion`/`intensity`
  implicitly overrides the state's influence for that line (the stored
  `speakerState` value is retained as evidence of what the model saw, not
  silently discarded).

### 3.5 Per-character delivery baseline

A snapshot reference into the character's casting profile, so a normally-terse
character shouting reads differently from a normally-verbose one shouting —
exactly the deviation-from-norm principle
[`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md) S5
already calls out and [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md)'s
`speechStyle`/`CastingSpec.timbrePreference` already produce:

```json
"baselineRef": {
  "characterId": "chr_042",
  "register": "formal",
  "energyDefault": "medium",
  "timbrePreference": ["authoritative", "weary"],
  "profileVersion": "v3"
}
```

This is a **copied snapshot at inference time**, not a live join, for the same
reproducibility reason `tts-engine-strategy.md` §6.4 pins voice identities
rather than re-deriving them live: re-running inference later with an updated
character profile should be an explicit, auditable event, not a silent drift in
historical direction rows.

### 3.6 Full v2 schema

```json
{
  "scopeType": "segment",
  "scopeId": "seg_1187",
  "schemaVersion": "2.0.0",
  "pace": 1.0,
  "intensity": 0.62,
  "tone": "tense",
  "emotion": "tense",
  "deliveryModifiers": ["trembling"],
  "pauseBeforeMs": 0,
  "pauseAfterMs": 220,
  "stylePrompt": "tense, controlled, audiobook delivery",
  "emphasis": false,
  "whisper": false,
  "noSfx": true,
  "nonverbalEvents": [
    {"type": "breath", "charStart": 0, "charEnd": 0, "confidence": 0.71, "evidenceQuote": ""}
  ],
  "speakerState": {"agitation": 0.62, "fatigue": 0.30, "asOfSegmentId": "seg_1187"},
  "baselineRef": {
    "characterId": "chr_042", "register": "formal", "energyDefault": "medium",
    "timbrePreference": ["authoritative", "weary"], "profileVersion": "v3"
  },
  "confidence": 0.81,
  "beatId": "beat_scene0042_02"
}
```

`schemaVersion`, `deliveryModifiers`, `nonverbalEvents`, `speakerState`,
`baselineRef`, `confidence`, and `beatId` are new and optional
(`nonverbalEvents` and `deliveryModifiers` default to `[]`; `speakerState`,
`baselineRef`, `beatId` default to `null`; `confidence` defaults to `0.0` for
manually authored rows). `pace`, `intensity`, `tone`, `emotion`,
`pauseBeforeMs`, `pauseAfterMs`, `stylePrompt`, `emphasis`, `whisper`, `noSfx`
are unchanged from v1 in name, alias, type, and bounds.

## 4. Inference pipeline v2

Direction reuses the **same scene-window partition and resolved speaker roster**
that [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
S4 (speaker attribution) computes and caches — S3/S4/S5 all consume one shared
windowing pass, per that document's stage graph. This document specifies the
full internal design of S5 in detail; extraction-pipeline-v2's S5 section
sketches a single-call-per-window version, which the two-pass design below
supersedes and elaborates.

### 4.1 Context assembly

Every prompt in both passes is built from the same four ingredients:

1. **Window/scene text** — segment text, `TARGET`/`CONTEXT` marked exactly as
   the existing prompt convention (`direction.py:_llm_prompt`).
2. **Attributed speakers** — the S4 roster and per-segment resolved
   `characterId`/`"narrator"`, so the model reasons about *who* is speaking,
   not a free-form guess.
3. **Character speech-style profiles** — the S3 `speechStyle`/`traits`
   synthesis ([`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
   §S3 PROFILE) and casting's `CastingSpec.timbrePreference`
   ([`automatic-casting-v2.md`](../casting/automatic-casting-v2.md)), snapshotted
   into `baselineRef` (§3.5).
4. **Preceding scene emotional arc summary** — a one-line carry-over from the
   previous scene's arc manifest (§5), in the same spirit as
   `generative-sound-design.md`'s `precedingSceneAtmosphere` carry-over:
   `{"dominantMood": "tense", "tensionLevel": 0.55, "trend": "rising"}`. This is
   what lets a scene that opens mid-tension read as continuing tension rather
   than resetting to neutral at every scene boundary.

### 4.2 Two-pass design

**Why two passes.** A single per-window call (like v1's LLM refinement, and
like extraction-pipeline-v2's S5 sketch) derives a line's delivery from
*nearby lines' text*. It has no representation of "this is the moment the trap
springs" versus "this is throat-clearing exposition" — it can only pattern-match
locally. Splitting into a **beat pass** (what is dramatically happening) and a
**line pass** (how each line delivers that) lets the line pass answer a much
better-posed question: not "does this text sound urgent," but "given that this
window sits inside beat 3 of 5, a rising-tension confrontation, how does *this
character's* line land."

```
┌────────────────────────────────────────────────────────────────────┐
│ PASS 1 — Emotional beat analysis          unit = 1 scene            │
│  input:  scene text + roster + preceding-scene arc carry-over       │
│  LLM.large (few calls; scene-grained, richer reasoning affordable)  │
│  output: ordered beats [{spanSegmentIds, dominantEmotion,           │
│           tensionLevel, trend, rationale}], scene arc summary       │
└────────────────────────────────────────────────────────────────────┘
                              │  scene arc + beat sequence (feeds §5 manifest)
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ PASS 2 — Per-segment direction derivation   unit = 1 scene-window    │
│  input:  window (TARGET/CONTEXT) + roster + baselineRef + the beat  │
│           this window falls under + speakerState carried forward    │
│  LLM.small (reuses the S4 window partition; parallel, cached)       │
│  output: DirectionProfile per TARGET segment + nonverbal spans      │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              CONSISTENCY SMOOTHING (deterministic, §4.4)
                              │
                              ▼
              VALIDATION / GUARDRAILS (deterministic, §6)
```

**Pass 1 — emotional beat analysis (unit = 1 scene, `LLM.large`).** Reuses
scene boundaries from S2/S4, not S4's finer scene-window split — a beat is a
narrative unit, and chopping it at an arbitrary 15-segment window boundary would
defeat the point. A scene under the existing cast-discovery bound
(`CAST_WINDOW_MAX_CHARS = 6000`) is one call; a longer scene splits into
overlapping beat-sub-windows using the same bounding logic
`direction.py:_bounded_scene_window` already implements, generalized from
segment-target-bounded to beat-bounded, with the trailing beat's state carried
as context into the next sub-window (no separate LLM reduce needed — beats are
sequential, non-overlapping narrative moments, not a global reconciliation
problem like structure boundaries).

Prompt design notes:
- System instruction: *"You read one scene and identify its emotional beats —
  points where the dramatic tone shifts. Use only what the text supports. A
  beat groups consecutive segments that share one dominant emotional register."*
- Input: scene text with segment boundaries marked (offsets, not re-quoted
  text, mirroring S2's discipline), the roster, and the preceding-scene arc
  carry-over.
- Output schema (`format=<json schema>`, `temperature=0`, one retry on schema
  failure — the existing `local_llm.py` contract):

```json
{
  "beats": [
    {
      "beatId": "beat_scene0042_01",
      "spanSegmentIds": ["seg_1180", "seg_1181", "seg_1182"],
      "dominantEmotion": "tense",
      "tensionLevel": 0.55,
      "trend": "rising",
      "rationale": "Two characters circle an unspoken accusation."
    }
  ],
  "sceneArc": {"dominantMood": "tense", "peakTensionLevel": 0.82, "overallTrend": "rising"},
  "confidence": 0.79
}
```

Because Pass 1 runs at scene grain rather than window grain, it is a
comparatively small number of calls (§8) even though it uses the larger,
better-reasoning `LLM.large` tier by default (§8, Model Center).

**Pass 2 — per-segment direction derivation (unit = 1 scene-window,
`LLM.small`).** Runs on the *exact same* window partition S4 already computed
and cached, so it shares that partition's caching/checkpoint unit. Prompt
carries the window's `TARGET`/`CONTEXT` segments, the roster, each target's
`baselineRef`, the Pass 1 beat(s) the window falls under (with `rationale`), and
the running `speakerState` for each active speaker (threaded window-to-window
within the scene, same pattern as S4's conversation-state threading). Output:
one `DirectionProfile` (minus `beatId`, which the runner fills in from Pass 1's
span lookup) per `TARGET` segment, plus any evidence-gated `nonverbalEvents`.

```
def infer_direction(scene_windows, beats_by_scene, rosters, baselines):
    for scene in scenes:                                   # PASS 1, parallel across scenes
        arc = LLM.large(beat_prompt(scene, roster(scene), preceding_arc(scene)))
        beats_by_scene[scene.id] = arc.beats
        scene_arc_manifest[scene.id] = arc.sceneArc

    for window in scene_windows:                           # PASS 2, parallel across windows
        beat = lookup_beat(beats_by_scene, window)
        state_in = speaker_state_carry(window)              # from previous window in scene
        result = LLM.small(direction_prompt(window, rosters[window], baselines,
                                             beat, state_in))
        directions, state_out = result.directions, result.speakerStateOut
        emit(directions)
        carry_forward(window.scene_id, state_out)
```

### 4.3 Narration vs dialogue asymmetry

Narration must stay restrained even inside a highly charged scene — the
"conservative, tasteful" constraint made mechanical, and consistent with the
voice bible's `narrationRestraint: high` / `maxExpressiveness: medium` defaults
([`voice-bible-spec.md`](../casting/voice-bible-spec.md)). Pass 2 applies a hard
cap by segment type **before** validation (§6) ever needs to reject anything:

| Segment type | Intensity cap | `shout` allowed | `whisper` allowed | Notes |
|---|---|---|---|---|
| `narration` | `0.6` | no | yes | Restrained by default; can still go hushed. |
| `dialogue` / `dialogue_with_tag` | `1.0` | project-gated (`allowShouting`) | project-gated (`allowWhispering`) | Full range, subject to the voice bible's global toggles. |
| `action_beat` | `0.75` | no | yes | Between narration and dialogue — reads scene action, not spoken. |
| `heading` / `footnote` | `0.3` | no | no | Always near-neutral; these are never performed as drama. |

The cap is a ceiling applied to Pass 2's raw output
(`intensity = min(raw_intensity, cap[segment_type])`), and `allowShouting` /
`allowWhispering` come straight from the project's voice bible `globalRules`
(§8 wires this read). This is what stops a narrator from "shouting" a battle
description even when the scene's `sceneArc.peakTensionLevel` is `0.95` — the
tension is real and drives dialogue delivery, but narration reports it, it does
not perform it.

### 4.4 Consistency smoothing (hysteresis)

Per-line variance from Pass 2 can still whiplash between adjacent segments
inside the *same* beat (two consecutive lines independently scored `tense` then
`bright` from marginal wording differences, with no beat change to justify it).
A deterministic post-pass smooths this **only when it is not beat-justified**:

```python
def smooth_scene(segments_in_order, beats):
    for i, seg in enumerate(segments_in_order[1:], start=1):
        prev = segments_in_order[i - 1]
        same_beat = beat_of(seg) == beat_of(prev)
        dist = EMOTION_DISTANCE[prev.emotion][seg.emotion]     # adjacency graph, 0..1
        if same_beat and dist > WHIPLASH_THRESHOLD and seg.confidence < HIGH:
            seg.emotion = prev.emotion
            seg.intensity = (prev.intensity + seg.intensity) / 2
            seg.evidence["smoothed"] = {"from": seg.emotion, "reason": "same-beat hysteresis"}
        # a beat change (same_beat == False) or a high-confidence jump is a
        # real narrative swing and is never smoothed — that is the entire
        # point of grounding delivery in beats rather than lines.
```

`EMOTION_DISTANCE` is a small hand-curated adjacency table (e.g.
`tense↔urgent` is close/`0.2`; `tense↔bright` is far/`0.9`), analogous in spirit
to `automatic-casting-v2.md`'s small hand-curated `ROLE_TIMBRE_DEFAULTS` table —
intentionally small, inspectable, and versioned rather than learned. Smoothing
only ever pulls a *low-confidence*, *same-beat* outlier back toward its
neighbor; it never overrides a genuine beat boundary or a high-confidence
result, so real dramatic swings always survive.

### 4.5 Confidence + evidence, three-tier policy

Applied uniformly with [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
three-tier model (illustrative thresholds, calibrated empirically per that
document's §Confidence & flag model process — not guessed here):

| Tier | Condition | Action |
|---|---|---|
| Auto-accept | `confidence ≥ 0.75` | Apply silently; evidence retained (`beatId`, `llmRunId`, window). |
| Auto-accept, audited | `0.45 ≤ confidence < 0.75` | Apply, tag `autoAccepted=true`, visible in an optional spot-check view. |
| Flag | `confidence < 0.45` **after** the window's own re-ask (one bounded retry with the beat rationale re-stated) still lands low | Keep the previous/deterministic direction in place; open a grouped review task. |

**What actually triggers a flag** (direction "almost never flags," but these
are the genuine cases):
- A segment's Pass 2 confidence stays below `MID` even after retry — usually a
  scene whose tonal register the beat pass itself scored low-confidence (e.g. a
  genuinely ambiguous dark-comedy scene).
- A nonverbal event's `evidenceQuote` fails the verbatim-substring check (§6) —
  the model claimed evidence that is not actually in the text; never silently
  dropped, always surfaced.
- A validation guardrail (§6) fires a violation that cannot be auto-repaired
  deterministically (e.g. both `whisper` and `shout` requested with equal
  confidence and no clear tiebreak).

Flags are **grouped**, never per-segment noise: "Chapter 12: 5 segments have
low-confidence delivery direction (ambiguous scene tone)" is one review task
carrying all five segments' evidence, matching
[`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
aggregation model exactly (category `direction`, severities `info`/`warning`,
existing `issues` mechanism — no new review-queue concept).

## 5. Scene emotional arc manifest

Pass 1 (§4.2) already produces the full beat sequence and scene-level summary
as a side effect of deriving per-line direction — this manifest is that output
made durable and directly consumable by
[`generative-sound-design.md`](../assembly/generative-sound-design.md) for
music placement (its "genuine emotional peak" rule keys off exactly this kind
of tension signal).

```json
{
  "manifestType": "direction_manifest",
  "schemaVersion": "2.0.0",
  "projectId": "proj_001",
  "chapterId": "chap_012",
  "generatedAt": "2026-07-07T00:00:00Z",
  "generator": {"service": "direction-service", "version": "2.0.0"},
  "status": "completed",
  "diagnostics": [],
  "payload": {
    "sceneArcs": [
      {
        "sceneId": "scene_0042",
        "dominantMood": "tense",
        "peakTensionLevel": 0.82,
        "overallTrend": "rising",
        "beats": [
          {"beatId": "beat_scene0042_01", "spanSegmentIds": ["seg_1180", "seg_1181"],
           "dominantEmotion": "tense", "tensionLevel": 0.55, "trend": "rising"},
          {"beatId": "beat_scene0042_02", "spanSegmentIds": ["seg_1182", "seg_1183", "seg_1184"],
           "dominantEmotion": "fearful", "tensionLevel": 0.82, "trend": "rising"}
        ],
        "confidence": 0.79,
        "llmRunId": "llmrun_9c21…"
      }
    ]
  }
}
```

**Coordination note.** `generative-sound-design.md` already specifies its own,
independently-run atmosphere-profile call, one per scene, which produces a
structurally similar `tensionArc: {level, trend}` and a `mood` field drawn from
a deliberately overlapping vocabulary (§3.1 above). The two passes currently
read the same scene text for related-but-distinct purposes (sound design needs
location/weather/explicit sound events too; direction needs beats and per-line
implications). This document's `sceneArcs` payload is deliberately shaped to be
trivially projectable into that document's `tensionArc`/`mood` fields
(`peakTensionLevel → tensionArc.level`, `overallTrend → tensionArc.trend`,
`dominantMood → mood`), so a future revision could let sound design consume
this manifest directly instead of running a second, partially redundant LLM
call — flagged as an open question in §10 rather than resolved here, since
`generative-sound-design.md` is out of scope to modify from this document.

## 6. Validation & guardrails

All checks are deterministic, run after Pass 2 and smoothing, before a row is
persisted. A violation that has a well-defined deterministic repair is
auto-repaired and logged in evidence; a violation with no safe deterministic
repair becomes a flag (§4.5), never a silent guess.

| Check | Rule | On violation |
|---|---|---|
| Emotion vocabulary membership | `emotion ∈` the §3.1 controlled set | Reject row; keep previous direction; flag. |
| Numeric bounds | `pace ∈ [0.5, 2.0]`, `intensity ∈ [0.0, 1.0]`, pauses `∈ [0, 5000]` ms | Clamp (existing `_bounded_float`/`_bounded_int` pattern, unchanged). |
| Intensity caps by segment type | Table in §4.3 | Clamp down to the cap; log `{"cappedFrom": raw, "cappedTo": cap, "reason": "segment_type"}`. |
| `whisper` + `shout` mutual exclusion | Never both true / both present in `deliveryModifiers` | Keep whichever has higher associated confidence; drop the other; log both raw values. If confidences are within `0.05`, flag instead of guessing. |
| Nonverbal evidence integrity | `evidenceQuote` (if non-empty) must be a verbatim substring of `text_content[charStart:charEnd]`; spans must be in-bounds and non-overlapping per segment | Drop the offending event; flag if it was the sole evidence for a high-`confidence` claim. |
| Nonverbal budget per chapter | `NONVERBAL_BUDGET_PER_CHAPTER` (default 6, project-configurable) — same "restraint via budget" pattern as `generative-sound-design.md`'s SFX budget | Lowest-confidence events beyond the budget are skipped and logged, never silently dropped without a trace. |
| Style-prompt length | `stylePrompt` truncated to 240 chars (existing `_style_prompt` behavior, unchanged) | Truncate. |
| Project taste gates | `allowShouting`/`allowWhispering` from the voice bible `globalRules` | If a project disables shouting, any `shout` modifier is stripped and intensity is capped instead (never silently re-labeled as a different emotion). |

### Staleness / fingerprint rules

`direction_fingerprint` (existing: `sha256` over the normalized `direction_json`
payload, `direction.py:_save`) is extended to hash the full v2 payload,
including `nonverbalEvents`, `speakerState`, and `baselineRef` — any change to
those fields already changes the fingerprint today because they live inside the
same JSON blob column (`segment_directions.direction_json`,
`libs/db/src/echodraft_db/models.py:534`); no schema change is required for the
fingerprint mechanism itself. What v2 adds is **when the pipeline decides to
re-derive**, not just re-hash:

| Trigger | Scope of re-inference | Notes |
|---|---|---|
| Segment `text_content` changes | Re-run Pass 2 for that segment's window (offsets in `nonverbalEvents` are invalidated by definition) | Locked rows are skipped, exactly as today. |
| Speaker attribution changes for the segment | Re-run Pass 2 for that segment's window (roster/baseline changed) | Sibling-propagation-aware, mirroring attribution's own propagation. |
| Roster composition changes elsewhere in the window | Re-run Pass 2 for the whole window | A new speaker entering a window can shift `speakerState` for everyone in it. |
| Character's S3 speech-style profile changes upstream | Re-run Pass 2 only for that character's unlocked segments project-wide | Bounded, evidence-tracked — the same "only affected units recomputed" cache-invalidation principle as [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md). |
| Scene structure changes (segment moves between scenes) | Re-run Pass 1 for the affected scene(s), then cascading Pass 2 | Rare; structural edits already trigger broader re-extraction. |
| `user_locked = true` | Never re-inferred by any of the above | Unchanged v1 guarantee. |

Because the fingerprint already participates in the render cache key
([`direction-studio.md`](direction-studio.md) "Production Resolution"), any of
the above re-inferences stales only the affected segments' cached renders —
never a whole-chapter re-render — matching constraint 3 (patchability).

## 7. User override model

- **Per-segment override** — unchanged surface: `PUT
  /api/v1/projects/{projectId}/segments/{segmentId}/direction` accepts the full
  v2 `DirectionProfile` (all new fields optional); `userLocked=true` removes the
  segment from every re-inference trigger in §6's staleness table, exactly as v1.
- **Per-character delivery baseline override** — new. A user can set a
  character-level bias (e.g. "Captain Reyes should generally read more
  weary/less energetic than the auto-derived baseline") via
  `PUT /api/v1/projects/{projectId}/characters/{characterId}/direction-baseline`.
  This does not retroactively rewrite existing segment rows; it biases
  `baselineRef` for **future** Pass 2 runs for that character, the same
  "propose, don't silently clobber" discipline
  [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md) uses for
  casting reruns. A separate explicit action
  (`POST .../direction-baseline/reapply`) re-runs Pass 2 for that character's
  currently-unlocked segments only, if the user wants the bias applied
  retroactively.
- **Scene-level arc lock** — new. Because one Pass 1 beat sequence feeds many
  segments' Pass 2 derivation, a coarse lock is needed above the segment level:
  `POST /api/v1/projects/{projectId}/scenes/{sceneId}/direction/lock` pins the
  scene's beat sequence so re-running direction inference (e.g. after an
  unrelated chapter edit triggers a book-wide rerun) never regenerates that
  scene's dramatic shape out from under a reviewer who has already approved it.
  Segment-level locks inside a locked scene remain independently toggleable.
- **Re-render invalidation stays targeted.** A segment-level edit stales only
  that segment's render key (existing mechanism, §6). A character-baseline
  reapply stales exactly that character's affected segments, nothing else — no
  new invalidation logic is needed beyond what the fingerprint chain already
  does.
- **Preview loop.** The existing `preview()` path
  (`DirectionService.preview`, writes to `audio/previews/` plus a
  non-committal `direction_manifest.json`) is unchanged in mechanism and
  extended to accept the v2 payload: a user editing a segment's direction can
  audition it immediately through whichever engine tier is active, via
  [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md)'s `compile_direction`,
  without writing a `SegmentRenderRecord` or affecting render history.

## 8. Data model, API, and manifest impact

Coordinate with [`domain-model-v2.md`](../../domain/domain-model-v2.md) and
[`api-v2-contracts.md`](../../api/api-v2-contracts.md) (in progress in
parallel) — this section is the direction-owned slice they should incorporate.

### Data model

Because `segment_directions.direction_json`
(`libs/db/src/echodraft_db/models.py:529`) already stores the full
`DirectionProfile` as a JSON blob, **every §3 field addition
(`deliveryModifiers`, `nonverbalEvents`, `speakerState`, `baselineRef`,
`confidence`, `beatId`) requires zero new columns** — it lands inside the
existing blob, exactly like `noSfx` did when it was added. Two genuinely new
pieces of state need first-class storage:

- **New table `scene_direction_arcs`** — `id, project_id, scene_id, chapter_id,
  dominant_mood, peak_tension_level, overall_trend, beats_json, confidence,
  algorithm_version, llm_run_id, user_locked, created_at`. The manifest file
  (§5) is the durable source of truth per
  [`pipeline-manifest-spec.md`](../../architecture/pipeline-manifest-spec.md);
  this table is a lightweight read-model so the API can query scene arcs
  without parsing the whole chapter manifest per request — the same
  manifest-plus-read-model split `casting_decisions` uses in
  [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md).
- **New table `character_direction_baselines`** — `character_id, project_id,
  bias_json, locked_reason, updated_at`, holding the §7 per-character override
  bias that Pass 2 reads in addition to the live `baselineRef` snapshot.

### API

| Endpoint | Change |
|---|---|
| `GET/PUT .../segments/{segmentId}/direction` | Unchanged surface; payload gains v2 fields (additive). |
| `POST .../directions/infer` | Request shape unchanged (`useLocalLlm`/`model`); internally now always runs the two-pass pipeline through the shared parallel LLM worker pool (§4) rather than the sequential v1 path — this is an implementation change behind the same contract, not a breaking one. |
| `GET .../direction/scene-arcs` | **New.** Lists `scene_direction_arcs` rows for a project/chapter. |
| `PUT .../characters/{characterId}/direction-baseline` | **New.** Sets the §7 per-character bias. |
| `POST .../characters/{characterId}/direction-baseline/reapply` | **New.** Re-runs Pass 2 for that character's unlocked segments. |
| `POST .../scenes/{sceneId}/direction/lock` | **New.** Scene-level arc lock (§7). |

### Model Center

Following [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
tiering table: Pass 2 (line derivation, the high-volume call) runs on
`qwen3:4b` (`qwen3_4b_ollama`, `LLM.small`), identical to S4 attribution — no
new catalog entry needed. Pass 1 (beat analysis) defaults to the `LLM.large`
reconciliation-tier model already proposed for S2/S3/S4 reduce/reconcile steps,
because its call volume is low (§ below) and beat quality benefits from the
larger model's narrative reasoning; on hardware where only the small model is
installed, Pass 1 **falls back to `LLM.small` with a lower `HIGH` confidence
threshold** — the same honest-degradation pattern used everywhere else in
extraction v2 (more items land in the audited tier, never a silent quality claim).

### Performance budget

v1 has no separately measured wall-clock figure for direction alone in the
shared research (it shares the same sequential-Ollama-call bottleneck the other
LLM passes have when `useLocalLlm=true`, and is skipped by default otherwise —
so today's "fast" path is fast only because it is shallow). v2's budget is
computed as an addition to
[`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
worked example for the reference 500-page book (~6,995 segments, ~470
scene-windows at ~15 segments/window):

```
Existing budget (extraction-pipeline-v2, all 5 stages):  units ≈ 2000,  wall_clock ≈ 33 min  (P=4, T=4s)

Direction v2 adds:
  Pass 2 units  = scene-windows          ≈ 470   (same partition S4 already uses — this
                                                    replaces, not adds to, the ~470 units
                                                    extraction-pipeline-v2's S5 sketch
                                                    already budgeted)
  Pass 1 units  = scenes                 ≈ 180   (scenes are coarser than windows; a
                                                    scene typically spans 2–4 windows)
                                                    — this is the net NEW cost

  extra_units  ≈ 180
  extra_time  ≈ 180 × 4s / 4 ≈ 180 s ≈ 3 min     (Pass 1 uses LLM.large, slower per call
                                                    but far fewer calls; approximated at
                                                    the same P for a conservative bound)

  new wall_clock ≈ 33 min + 3 min ≈ 36 min       → still inside the 30–45 min mid-tier budget
```

On a GPU workstation (`T≈1s`, `P≈8–16` per
[`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)),
the addition is proportionally smaller and stays well inside the ≤12 min target.

## 9. Evaluation

**Labeled sample protocol.** Extend the same git-ignored, `test-assets/`-adjacent
golden-fixture corpus [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
defines (public-domain Gutenberg books) with a direction-labeled subset: two or
more human annotators independently label `{emotion, intensity band,
deliveryModifiers, nonverbal spans}` for a sample of segments drawn from at
least one high-drama scene, one low-key/expository scene, one comedic scene,
and one action scene per fixture book — deliberately covering the cases where
keyword heuristics fail worst (§2).

**Agreement metrics.** Direction is more subjective than structure/attribution,
so the target is agreement with human raters, not exact match against a single
gold label:
- **Inter-rater ceiling** — Cohen's κ between human annotators on `emotion`
  category, established first so model performance is judged against a
  realistic ceiling, not perfection.
- **Model-vs-human** — κ (or weighted κ, since some emotion pairs are "close")
  between the model's `emotion` and the majority human label; Spearman
  correlation on `intensity`; span-overlap F1 (IoU-style) on `nonverbalEvents`
  against human-marked spans.
- **Calibration** — the same isotonic/Platt fitting process
  [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
  §Confidence & flag model specifies, applied to this stage's `HIGH`/`MID`
  thresholds (§4.5's `0.75`/`0.45` are illustrative starting points, not fitted
  values).

**Listening A/B.** Render the same scene under v1 keyword-heuristic direction
and v2 two-pass direction through the identical TTS tier; blind listeners rate
"does this sound performed or read" and pick a preference, tracking a v2
win-rate — the same blind-comparison discipline
[`automatic-casting-v2.md`](../casting/automatic-casting-v2.md)'s "Sunday
Suspense yardstick" A/B uses for voice distinctness, applied here to delivery
instead of timbre.

## 10. Migration path, risks, and open questions

### Migration path (incremental, each step independently shippable)

1. **Schema foundations, no behavior change.** Add the v2 optional fields to
   the `DirectionProfile` domain model and the two new tables (§8); keep
   `direction.py`'s current `_infer`/`_normalized`/`CONTROLLED_EMOTIONS` path as
   the active default behind a flag. Existing rows keep validating unchanged.
2. **Move onto the shared worker pool.** Route direction's LLM calls through
   the parallel, cached LLM-worker pool
   [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)'s
   migration §1 builds for S2–S4, instead of `_apply_local_llm`'s bespoke
   sequential loop. No accuracy change expected at this step; it only removes
   the serial bottleneck.
3. **Ship the two-pass pipeline behind a flag.** Implement Pass 1 (beat
   analysis) and Pass 2 (line derivation) as specified in §4; keep v1's
   keyword `_infer` output as **deterministic evidence fed into Pass 2's
   prompt** rather than deleting it — the same "demote deterministic code to
   evidence" move [`extraction-pipeline-v2.md`](../../architecture/extraction-pipeline-v2.md)
   applies to every other stage.
4. **Add consistency smoothing and the §6 validation guardrails.** These are
   pure post-processing and can be evaluated against the harness (§9)
   independently of the two-pass change itself.
5. **Ship the three-tier confidence/flag model** and retire the current single
   "LLM direction inference skipped a segment window" warning category in
   favor of grouped review tasks (§4.5).
6. **Ship the v2 user override surfaces** (§7): character baselines, scene
   locks, reapply endpoints.
7. **Wire into `tts-engine-strategy.md`'s `compile_direction`** once that
   lands — a dependency, not a blocker: direction v2 is useful (richer,
   evidence-backed, cheaply producible metadata) even rendered through today's
   pace-and-pauses-only engines, exactly as v1 direction is today. The risk is
   letting this step lag indefinitely (see below).

### Risks

- **Vocabulary size creep.** Growing from 9 to 17 emotions plus 8 delivery
  modifiers risks a small local model's schema-constrained decoding becoming
  less reliable at the edges (e.g. `contemptuous` vs `angry` vs `defiant` are
  genuinely close). Mitigation: schema-constrained JSON enum decoding bounds
  the failure mode to "picks the wrong close label," never "invents a free-text
  value" — but real per-emotion precision needs measuring on the eval harness
  (§9), not assumed from the taxonomy design alone.
- **Nonverbal hallucination.** The evidence-gating rule (§3.3) is a hard
  requirement here, mirroring [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md)
  §5.2's "never invented from `emotion` alone." *Open:* the right confidence
  threshold below which an evidence-backed-but-marginal nonverbal claim should
  still be dropped rather than rendered.
- **Two-pass cost.** Adds roughly 180 extra LLM calls to the reference book's
  budget (§8) — small, but not free. *Open:* whether Pass 1's per-scene read of
  the manuscript can eventually be consolidated with cast discovery's (S3) or
  sound design's atmosphere-profile call, all three of which independently read
  the same scene text today. This document does not attempt that consolidation
  because `generative-sound-design.md` is already specified independently and
  out of scope to modify here — flagged for a future cross-cutting revision
  once all v2 stages exist and their actual measured costs are known.
- **Speaker-state continuity is inherently fuzzy.** `agitation`/`fatigue` are
  subjective, low-precision signals. *Open:* whether they measurably improve
  perceived performance quality enough to justify the added prompt complexity
  — the listening A/B (§9) should gate keeping them, not intuition.
- **The consumption gap is only half-closed.** This document fixes direction
  *quality*; it does not by itself make TTS sound different, because no
  shipped engine consumes the richer fields until
  [`tts-engine-strategy.md`](../tts/tts-engine-strategy.md)'s compiler and at
  least one Tier-S engine land. Shipping this document alone repeats v1's
  pattern (infer, don't consume) unless the two workstreams are sequenced
  together — this is a sequencing risk to track explicitly, not merely an
  academic non-goal.
- **Backward compatibility is achievable but not automatic for new fields.**
  Old `segment_directions` rows remain valid and renderable unchanged (§3), but
  they will not have `nonverbalEvents`/`speakerState`/`baselineRef` populated
  until re-inferred. *Open:* whether backfilling v2-only fields on existing
  projects should run automatically (as a low-priority background job) or stay
  strictly opt-in per project, given it touches potentially-reviewed direction
  rows.

### Open questions

- What is the right `NONVERBAL_BUDGET_PER_CHAPTER` default, and should it scale
  with chapter length rather than being a flat constant?
- Should `EMOTION_DISTANCE` (§4.4) be hand-curated (as proposed, for
  inspectability) or learned from the labeled eval set once enough labels
  exist?
- Does Pass 1 need its own self-consistency voting (like S4's low-confidence
  resampling) for scenes where the beat pass itself lands low-confidence, or is
  a single bounded retry (§4.5) sufficient?
- How much does `LLM.large` vs `LLM.small` actually change Pass 1 quality in
  practice, and is the extra model dependency worth it for a stage where call
  volume is already low? (Resolve at the same bake-off-style measurement
  extraction-pipeline-v2 and tts-engine-strategy.md both use for their own open
  questions.)
