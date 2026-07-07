# Generative Sound Design

Ambient sound effects and background music should be **AI-generated and automatically
inserted** — not user-uploaded. This document specifies how Echodraft gets from "a scene
of text" to "a tasteful, licensed, cached ambience/music/SFX layer sitting under the
narration," without asking the user to record or find a single sound file. It assumes and
extends the existing deterministic mixing engine documented in
[`sound-design.md`](sound-design.md) and implemented in
[`apps/api/src/echodraft_api/assembly.py`](../../../apps/api/src/echodraft_api/assembly.py)
(`ChapterAssembler`) — that engine (cues, crossfades, ducking, gain ceilings, mastering) is
correct and stays exactly as it is. What changes is **where the audio comes from** (a local
generative model or a licensed bank, never a user upload as the primary path) and **who
decides where it goes** (a deterministic planner reading extraction metadata, never a human
dragging a cue on a timeline as the primary path).

See also: [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) (scene
metadata and the parallel per-scene LLM window pattern this design reuses),
[target-architecture.md](../../architecture/target-architecture.md) (job/worker pool,
event push, and manifest invalidation this design plugs into),
[tts-engine-strategy.md](../tts/tts-engine-strategy.md) (the sibling generative-audio
problem for voice, and the GPU/hardware-tiering approach this document mirrors for audio
generation), [direction-studio.md](../direction/direction-studio.md) (the `DirectionProfile.noSfx`
field this design finally wires up), [pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md),
[db-schema.md](../../domain/db-schema.md), and [model-center.md](../../architecture/local-ai/model-center.md).

## Purpose

Turn the per-scene metadata the extraction pipeline already produces into an automatic,
local, licensed, restraint-first sound design layer: one ambience bed per scene at most,
music only at chapter openings or genuine emotional peaks, and sparse sound effects anchored
to explicit textual events — all generated or selected locally, cached, QA'd, and placed
through the existing cue/mix/master pipeline with zero required user action.

## Goals

- **Automatic by default.** A book that has never seen a human touch its sound design still
  gets tasteful `light_cinematic` ambience if the user picks that render mode. No upload, no
  manual cue placement, no asset hunting.
- **Local-first.** Every generation path — model inference or bank lookup — runs on the
  user's machine. Cloud generation is never required (constraint #4 in the brief; see
  `AGENTS.md`/`CLAUDE.md`).
- **Restraint-first.** "Conservative, tasteful audio production" is not a suggestion, it is
  the design's organizing constraint. The system defaults to *less* sound design, not more:
  one bed, sparse SFX, music that gets out of the way of dialogue.
- **Evidence-backed.** Every automatically placed cue records the scene text and rule that
  produced it, exactly like `speaker_attributions` records evidence for a casting decision
  (see [speaker-attribution.md](../casting/speaker-attribution.md)).
- **Editable, never a black box.** Everything generated is a normal `AmbienceAssetRecord` /
  `AmbienceCueRecord` row. Regenerate, mute, swap, or replace with an upload — the existing
  manual controls in [sound-design.md](sound-design.md) keep working unchanged, they simply
  stop being the *only* way sound design happens.
- **Reusable across a book and across a library.** A generated "rainy forest at night, tense"
  bed used in chapter 3 should be the same file used in chapter 19 of the same book, and in
  an unrelated book with a similar scene, via a content-addressed cache.
- **Never regress the clean-narration default.** `speech_only` chapters are unaffected by any
  of this. Generative sound design only activates in `light_cinematic` and `dramatized`
  modes, which must still be assembled explicitly.

## Non-goals

- **Full film-style scoring.** No leitmotifs, no continuous underscore tracking every beat,
  no multi-cue orchestral cues per paragraph. This is audiobook ambience, not a film score.
- **Per-line foley.** No footstep-per-step, no page-turn-per-page-turn, no effect for every
  physical action mentioned in the text. SFX is sparse and budgeted, not exhaustive.
- **Anything that competes with or distracts from narration.** If a listening test flags a
  cue as "noticeable in a bad way," the fix is to remove or quiet the cue, never to make the
  narration louder to compensate.
- **Real-time or interactive editing UI.** This document specifies the pipeline and data
  model; the sound-design panel's visual redesign belongs to
  [design-system.md](../../ui/design-system.md) and
  [frontend-architecture.md](../../ui/frontend-architecture.md).
- **Perfect SFX matching for unusual textual events.** A model asked for "the clockwork
  raven's wings creaking" may produce something generic. The mitigation is confidence
  gating, a strict budget, and one-click mute/regenerate — not a claim of perfect fidelity.
- **Cloud generation, ever, as a required path.** An optional cloud fallback is not part of
  this design; if one is ever added elsewhere, it must remain strictly optional per
  constraint #4.

## Current state and the gap

Today (per [sound-design.md](sound-design.md) and `ambience.py`/`assembly.py`):

- Sound assets are **upload-only**: `POST /api/v1/projects/{projectId}/sound-assets` and
  `.../sound-assets/from-path` accept local WAV files (or a local path Echodraft copies in);
  there is no generation of any kind.
- Cue placement is **entirely manual**: a human opens the Sound Design panel, picks a scene,
  picks an uploaded asset, and sets start offset/gain/fades/ducking/mode by hand for every
  single cue.
- The mixing engine that consumes those cues — loop crossfades, ducking, per-mode gain
  ceilings, mastering — is correct and complete. Nothing about *how a cue is mixed* needs to
  change.
- The extraction pipeline already produces rich per-scene structure (chapter/scene/segment
  boundaries, speaker attribution, direction) but **no atmosphere metadata** — nothing today
  tells the system "this scene is a rainy exterior at night" or "a door slams here."
- `DirectionProfile.noSfx` already exists in the schema (default `true`, and every
  LLM-inferred direction row sets it to `true` explicitly — see `direction.py:_direction_from_llm_payload`)
  but **nothing today ever produces an automatic SFX cue for it to suppress**. It is a
  no-op field waiting for a producer.

The gap is exactly the one the product mandate names: nobody generates the audio, and
nobody places it. Everything below fills that gap while leaving the mixing engine, the
manual upload path, and the manual cue API untouched and fully functional as the override
mechanism.

```
Today:      [user finds/records WAV] --upload--> [user places cue by hand] --> mixer --> master
Target:     [scene text] --atmosphere profile--> [sound planner] --> [asset resolver:
                                                                       cache | generate | bank]
                                                        |
                                                        v
                                          [auto-placed AmbienceCueRecord, origin=auto_generated]
                                                        |
                                                        v
                                          existing mixer (unchanged) --> existing master (unchanged)
            (manual upload + manual cue API remain available as an override at any point)
```

## Local generative audio model survey

As of early 2026, no single local model covers ambience, SFX, and music at a quality and
license profile good enough to be the *only* source. The design therefore treats generation
as a **tiered menu** behind Model Center, with a license-clean, always-available fallback
tier that never depends on any of these models being installed.

Everything below marked **(verify at bake-off)** is a claim that should be re-checked
against the actual released weights/license text before being surfaced to users, per
[model-center.md](../../architecture/local-ai/model-center.md)'s existing pattern of
explicit consent + license summaries per catalog entry.

### Survey table

| Model | Publisher | Capability | License | VRAM / CPU | Native duration | Loopability | Quality tier |
|---|---|---|---|---|---|---|---|
| **Procedural DSP + CC0 bank** | Echodraft-bundled | ambience (wind, rain, fire, room tone, crowd, ocean, forest, urban), simple percussive SFX | CC0 samples / code-owned synthesis — zero license risk | CPU only, negligible RAM | unlimited (synthesized/tiled to any length) | native — designed to loop | good-enough baseline; synthetic character on close listening |
| **Stable Audio Open 1.0** (and "Open Small") | Stability AI | ambience, SFX, short instrumental/percussion beds | Stability AI Community License — free for orgs/individuals under a revenue threshold, commercial license required above it **(verify threshold + current terms at bake-off)** | ~6–8 GB VRAM recommended, CPU fallback is slow **(verify at bake-off)**; "Open Small" targets edge/CPU-class hardware | ~47 s per generation (Open 1.0); shorter for "Small" **(verify)** | not native — needs post-hoc loop-splice (below) | best fidelity of the locally-runnable text-to-audio set; trained on licensed Freesound/Free Music Archive data, the cleanest training-data story of the group |
| **AudioCraft — AudioGen** | Meta | environmental sound / SFX | **CC-BY-NC 4.0 — non-commercial only.** This is a real, honest blocker: a commercially distributed audiobook cannot ship audio derived from these checkpoints without a separate commercial license Meta does not offer for this model family. | 2–16 GB VRAM depending on model size | ~10 s native, extendable via continuation | needs splice | good SFX realism; license is the disqualifying factor for production use |
| **AudioCraft — MusicGen** | Meta | instrumental music beds | **CC-BY-NC 4.0 — same non-commercial blocker as AudioGen.** | 2 GB (small) – 16 GB (large) | 30 s native, extendable | needs splice | strong melodic/harmonic quality; same licensing disqualification |
| **Tango / TangoFlux** | Declare Lab | general text-to-audio (SFX/ambience-capable); TangoFlux adds fast flow-matching inference | mixed across releases, at least one checkpoint historically CC-BY-NC-like **(verify exact license per checkpoint at bake-off — do not assume commercial-safe)** | TangoFlux is optimized for sub-second generation on a data-center GPU; consumer-GPU VRAM footprint **unconfirmed (verify at bake-off)** | ~30 s | needs splice | competitive quality, very fast inference; license status is the open question, not quality |
| **YuE** | HKUST / M-A-P | full song generation (verse/chorus, vocals + instruments) | reported permissive (Apache-2.0-family) by the project **(verify at bake-off)** | large — full-quality generation wants a high-VRAM GPU (~16–24 GB) **(verify at bake-off)** | multi-minute full songs | not applicable | wrong grain for this use case — it generates whole songs with vocals, not short instrumental underscore beds; **not recommended** as a Tier candidate, listed for completeness |
| **ACE-Step** | ACE Studio / StepFun | fast instrumental + vocal music generation | reported Apache-2.0 by the project **(verify at bake-off)** | moderate, marketed as consumer-GPU-friendly **(verify at bake-off)** | up to several minutes; Echodraft would only ever request short cues | needs splice, or generate directly at the target cue length | promising commercial-friendly license story; newest and least field-validated of the set — treat as an experimental bake-off candidate, not a launch dependency |

### Fallback tier: procedural + CC0 bank

This tier is not a downgrade to tolerate until generative models are installed — it is the
tier most consistent with "conservative, tasteful audio production," and it ships in the box
with zero downloads:

- **Bundled CC0 loop library.** A small, curated set of CC0-licensed ambience loops (rain,
  wind, room tone, fire crackle, distant crowd, ocean, forest, urban night) and a handful of
  one-shot SFX (door, footstep on wood/stone, thunder crack, gunshot, glass break), tagged
  with the same vocabulary the atmosphere profile uses (see below) so lookup is a tag match,
  not a generation call.
- **Procedural DSP synthesis** for the genuinely generic beds, generated with numpy exactly
  like `mastering.py`'s existing pink-noise room tone:
  - *Wind*: band-pass-filtered noise with a slow (0.05–0.2 Hz) amplitude LFO for gusting.
  - *Rain*: broadband filtered noise (intensity) layered with a sparse, randomized impulse
    train (droplet density) band-passed to a "patter" register.
  - *Room tone*: reuses `mastering.room_tone()` at ambience-bed durations instead of the
    fixed head/tail lengths.
  - *Fire*: filtered noise bursts (crackle) over a low steady broadband bed (the "roar").
  - *Thunder*: a long, heavily low-pass-filtered noise burst with an exponential decay
    envelope and an optional short high-frequency "crack" transient at onset.
  - All procedural generators emit natively loopable output (they are stationary random
    processes; a loop point only needs the same 250 ms equal-power crossfade the mixer
    already applies at loop seams).
- **Zero license risk, zero network dependency, zero extra VRAM.** This tier is `required:
  true` in the Model Center catalog and always installed.

### Tiering recommendation

| Tier | Contents | Default state | Rationale |
|---|---|---|---|
| **Tier 0 — always available** | Procedural DSP + bundled CC0 bank | Installed by default, active as soon as `light_cinematic`/`dramatized` is used | License-clean, offline, fast, and often indistinguishable from a generated bed for generic atmospheres (wind, rain, room tone). This is the floor everyone gets. |
| **Tier 1 — recommended optional install** | Stable Audio Open (ambience/SFX/short music) | Opt-in via Model Center, one explicit consent screen (network download + license) | Best quality-to-license tradeoff of the generative options; its community license has a real (if imperfect) path to commercial use. |
| **Tier 2 — power-user / non-commercial only** | AudioCraft AudioGen + MusicGen | Opt-in, gated behind a second, stronger warning ("non-commercial license — do not use if this audiobook will be sold or published commercially") | Quality is good, but the CC-BY-NC license makes it unsafe as a silent default; users who only ever produce personal/non-commercial audiobooks can still benefit. |
| **Tier 3 — experimental / bake-off candidates** | TangoFlux, ACE-Step, YuE (tracked, not recommended) | `status: experimental` in the catalog, hidden behind an "experimental models" settings toggle | Needs a real bake-off (license re-verification, blind listening, resource cost) before promotion to Tier 1/2. Nothing here should be silently upgraded to a default. |

Chapter production settings expose one control that matters to the user: which tier(s) are
enabled for this project. The sound planner (next section) is tier-agnostic — it always
produces the same abstract "sound plan," and the asset resolver decides, per cue, which
installed tier actually renders it, cascading Tier 1/2 → Tier 0 on failure or when nothing
beyond Tier 0 is installed (`AGENTS.md` constraint: local-first, no mandatory downloads).

## Scene → sound-plan derivation

This is the core algorithm: text in, a placed, budgeted, license-clean sound plan out. It
has two stages — an LLM call that reads the scene and writes an **atmosphere profile**, and
a deterministic **sound planner** that turns atmosphere profiles into a **sound plan**. Only
the first stage touches an LLM; the mapping from profile to plan is pure, testable, and
auditable code, matching the rest of Echodraft's "deterministic rule cascade, LLM only where
deterministic rules run out" style (see [speaker-attribution.md](../casting/speaker-attribution.md)).

### Atmosphere profile: one LLM call per scene

Structure extraction already segments the manuscript into chapters → scenes → segments
before this stage runs. The atmosphere profile call adds one schema-constrained LLM call
**per scene**, reading that scene's text (bounded to the same kind of character-capped
window cast discovery already uses for its per-scene mention pass) and returning a small,
fixed JSON object.

This call has a property none of the existing extraction LLM calls have: **zero
cross-scene ordering dependency.** Cast discovery's dedupe and speaker attribution's
propagation both depend on prior decisions; atmosphere-profile extraction does not — scene
17's atmosphere has no bearing on how scene 3's LLM call is prompted or scored. That makes
it one of the most parallelizable calls in the whole pipeline: it can run across the full
window-worker pool described in [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)
with every scene in flight simultaneously, bounded only by worker-pool size, not by any
sequencing rule.

Prompt shape (schema-constrained JSON, same `format:<json schema>`, `temperature 0`,
one-retry-on-schema-failure convention as the existing local LLM calls in `local_llm.py`):

```
System: You read one scene from a novel and describe its physical/emotional atmosphere
for a sound designer. Only report what the text supports. Return strict JSON matching
the schema. If nothing suggests a detail, use the "unspecified"/none value — never invent.

Context:
  chapterTitle: "The Long Road South"
  precedingSceneAtmosphere: { location: "forest road", timeOfDay: "dusk", mood: "wary" }  (optional, 1-line carry-over)

Scene text (bounded window, same char cap as cast-discovery scene windows):
  <scene text>
```

Output schema:

```json
{
  "sceneId": "scene_0042",
  "location": { "description": "a dim tavern back room", "category": "tavern" },
  "timeOfDay": "night",
  "weather": "none",
  "interiorExterior": "interior",
  "mood": "tense",
  "tensionArc": { "level": 0.65, "trend": "rising" },
  "era": "historical_pre_industrial",
  "explicitSoundEvents": [
    {
      "eventType": "door_slam",
      "sentenceEvidence": "The door slammed shut behind him.",
      "confidence": 0.92
    }
  ],
  "noSfxRecommended": false,
  "confidence": 0.81
}
```

Field notes:

- `location.category` is drawn from a small controlled vocabulary (tavern, forest, city
  street, ocean/ship, battlefield, domestic interior, office, wilderness-camp, vehicle,
  courtroom, prison, market, generic-interior, generic-exterior, unspecified, …) so the
  planner and the Tier-0 bank lookup can both do exact/nearest-tag matching instead of
  fuzzy free-text matching.
- `timeOfDay` ∈ {dawn, morning, midday, afternoon, dusk, evening, night, unspecified}.
- `weather` ∈ {clear, rain, storm, snow, wind, fog, none, unspecified}.
- `mood` is drawn from a controlled vocabulary that deliberately overlaps
  `DirectionProfile`'s controlled emotion vocabulary (`neutral, warm, tense, quiet, urgent,
  somber, bright, fearful, angry`) plus a few scene-level additions (`calm, joyful,
  romantic, eerie, action`), so ambience mood and delivery direction stay coherent for the
  same scene.
- `tensionArc.level` is a 0–1 self-reported intensity for *this* scene only; the planner
  compares it across the chapter to find peaks (below), it does not compare across chapters.
- `explicitSoundEvents[].eventType` is drawn from a controlled vocabulary (door_slam,
  gunshot, thunder, glass_break, footsteps_running, phone_ring, explosion, scream,
  applause, engine_start, knock, …) — an open-ended free-text event type would make the
  SFX bank/prompt-construction step in the next section unbuildable.
- `sentenceEvidence` must be a **verbatim or near-verbatim substring of the scene text** —
  this is what the SFX time-anchoring algorithm locates in the segment timeline, and what
  the cue's evidence trail shows the user ("why does this door-slam SFX exist? — because of
  this sentence").
- `confidence` and per-event `confidence` gate everything downstream: low-confidence
  profiles skip ambience selection entirely rather than guess; low-confidence events never
  spend SFX budget.

### Sound planner: atmosphere profile → sound plan

The planner is deterministic, pure, and chapter-scoped: given the ordered list of a
chapter's scenes and their atmosphere profiles, plus the target render mode and the
project's sound-design settings, it emits an ordered list of planned ambience/music/SFX
placements *before* any asset exists. Asset resolution (generate/cache/bank) and cue
materialization happen after planning, in the next two sections — this keeps "what sound
should exist here" auditable and testable independently of "which model rendered it."

Rules encoded in the planner (each one is a restraint-first guardrail, not an optimization):

1. **Clean narration is untouched.** `speech_only` produces an empty plan; the planner is
   never invoked for that mode.
2. **At most one ambience bed per scene.** A scene never gets two competing ambience layers.
3. **Bed continuity across contiguous scenes.** If consecutive scenes share the same coarse
   "bed signature" (`locationCategory`, `interiorExterior`, `weather`, `timeOfDay`), the
   planner reuses the previous scene's ambience choice instead of re-selecting or
   re-triggering — a chapter that stays in the same tavern for three scenes gets one
   continuous bed, not three re-triggered ones.
4. **Music only at chapter openings or genuine emotional peaks**, and even then, at most
   once for an opening and once for a peak per chapter (dramatized mode only for the peak
   case; light mode gets opening music only). A "peak" requires `tensionArc.level >= 0.8`
   *and* a rise of at least `0.3` over the previous scene's level — a single arbitrary
   high-tension scene at the very start of a quiet chapter is not, by itself, a peak.
5. **SFX is sparse and budgeted.** A strict per-chapter SFX budget (default: 2 in
   `light_cinematic`, 5 in `dramatized`, configurable per project) caps how many explicit
   textual events become cues; once the budget is spent, remaining events in that chapter
   are skipped and logged, never silently exceeded.
6. **No-SFX flag is respected before spending budget.** An event is only eligible if the
   segment it anchors to does not resolve to `DirectionProfile.noSfx == true` (see
   [Taste guardrails](#taste-guardrails-machine-checked)) and the scene's own
   `noSfxRecommended` is false.
7. **SFX never competes with a concurrent music cue.** If a music cue's active window
   overlaps an SFX event's anchor time, the SFX is skipped (logged), preserving the
   "speech + 1 ambience + 1 of {music, sfx}" layering ceiling — see guardrails.
8. **Confidence gates everything.** Below a minimum scene-profile confidence, no ambience
   bed is chosen for that scene (silence is always a safe fallback; a wrong-mood bed is not).

Pseudocode:

```python
def plan_chapter_sound(chapter, scenes, mode, profiles, settings):
    if mode == "speech_only":
        return SoundPlan(chapter.id, cues=[])

    budget = settings.sfx_budget[mode]          # e.g. light=2, dramatized=5
    used_sfx = 0
    plan = SoundPlan(chapter.id, cues=[])
    prev_signature = None
    prev_bed_choice = None
    running_max_tension = 0.0
    opening_music_placed = False
    peak_music_placed = False

    for index, scene in enumerate(scenes):
        profile = profiles.get(scene.id)
        if profile is None or profile.confidence < MIN_SCENE_CONFIDENCE:
            prev_signature, prev_bed_choice = None, None   # do not guess; break continuity
            continue

        # --- ambience: at most one bed per scene, reused across a contiguous same-bed run
        signature = (profile.location.category, profile.interior_exterior,
                     profile.weather, profile.time_of_day)
        if not profile.no_sfx_recommended:
            bed_choice = prev_bed_choice if signature == prev_signature else select_bed(profile)
            if bed_choice is not None:
                plan.add_ambience(scene, bed_choice, continued=(signature == prev_signature))
            prev_signature, prev_bed_choice = signature, bed_choice

        # --- music: chapter open, or one genuine peak, never both loosely
        if index == 0 and settings.allow_opening_music and not opening_music_placed:
            plan.add_music(scene, select_theme(profile), position="chapter_open")
            opening_music_placed = True
        elif (mode == "dramatized" and not peak_music_placed
              and profile.tension_arc.level >= PEAK_LEVEL
              and profile.tension_arc.level - running_max_tension >= PEAK_DELTA):
            plan.add_music(scene, select_underscore(profile), position="emotional_peak")
            peak_music_placed = True
        running_max_tension = max(running_max_tension, profile.tension_arc.level)

        # --- sfx: sparse, budgeted, confidence- and flag-gated, never under music
        for event in profile.explicit_sound_events:
            if used_sfx >= budget:
                plan.log_skip(scene, event, reason="chapter_sfx_budget_exhausted")
                continue
            if event.confidence < SFX_MIN_CONFIDENCE:
                continue
            anchor = locate_segment_offset(event.sentence_evidence, scene)
            if anchor is None:
                plan.log_skip(scene, event, reason="no_timeline_anchor")
                continue
            if resolve_direction(anchor.segment_id).no_sfx:
                plan.log_skip(scene, event, reason="segment_no_sfx_flag")
                continue
            if plan.overlaps_music_window(anchor):
                plan.log_skip(scene, event, reason="overlaps_music_cue")
                continue
            plan.add_sfx(scene, event, anchor)
            used_sfx += 1

    return plan
```

`select_bed`, `select_theme`, and `select_underscore` are the prompt-construction functions
in the next section; `locate_segment_offset` and `resolve_direction` are described under
[Automatic cue placement](#automatic-cue-placement). The planner itself never calls a
model and never touches the filesystem — it is a pure function from
`(scenes, profiles, mode, settings)` to a `SoundPlan`, which makes it unit-testable without
any generative model installed.

The planner's output is persisted as a `sound_plan_manifest.json` per chapter (new manifest
type, `schemaVersion: "0.1.0"`, following the common envelope in
[pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md)) before asset
resolution runs, so "what the planner decided" and "what actually got rendered/cached" are
separately inspectable and separately debuggable.

## Asset generation and caching

Once the planner has decided *that* a bed/theme/SFX belongs at a given scene, the asset
resolver decides *which file* satisfies it — generating one, pulling one from cache, or
matching one from the Tier-0 bank.

### Prompt / bank-query construction

For a generative model (Tier 1/2/3), the atmosphere profile is rendered into a natural-language
prompt via a fixed template per cue kind:

```
Ambience: "{weather-or-interior-exterior} {location.description}, {timeOfDay}, {mood} atmosphere,
subtle continuous background texture, no music, no melody, no voices, no words, loopable"

Music (chapter open):  "instrumental scene-setting theme, {mood}, {era}, understated, no vocals,
no lyrics, short intro cue, gentle dynamics"

Music (emotional peak): "instrumental underscore, {mood}, tension rising, understated, no vocals,
no lyrics, short cue, must sit quietly under narration"

SFX: "{eventType}, single clean one-shot sound effect, no music, no ambience bed, no reverb tail
longer than natural"
```

The explicit negative phrasing (`no music, no vocals, no words`) exists because text-to-audio
models are known to hallucinate mumbled vocals or hummable melodies inside "ambience-only"
prompts — this is also caught mechanically by the tonal-artifact QA check below, but the
prompt is the first line of defense.

For the Tier-0 fallback, the same atmosphere fields collapse into a **tag query** against the
bundled bank's tag index instead of a natural-language prompt: `{locationCategory,
interiorExterior, weather, timeOfDay}` scored against each bank entry's tags (Jaccard
overlap), picking the best match; if no close match exists, the query degrades to the most
general applicable tag (e.g., a "tavern, night" miss falls back to a generic "interior room
tone" bed) rather than returning nothing. A DSP-procedural generator is used directly (no
lookup) for the small set of atmosphere signatures it covers natively (wind/rain/fire/room
tone/thunder).

### Target duration and loopable generation strategy

Ambience beds target a base loop unit of **20–30 seconds** — long enough that the loop point
is not obviously audible, short enough to fit comfortably under every Tier-1 model's native
duration ceiling (Stable Audio Open's ~47 s) and to keep generation cost low. Music cues
target their actual placement duration directly (a chapter-opening fade is a few seconds; an
underscore cue is bounded by the scene's paragraph/segment timing, see below) rather than
being looped.

Making a generated clip loop seamlessly is a three-step pipeline, reusing existing mixer
primitives wherever possible instead of inventing new ones:

1. **Over-generate.** Request slightly more than the target duration (target + one crossfade
   window) so there is real material to splice from, rather than looping the exact requested
   length with no slack.
2. **Seam search.** Scan candidate splice points near the tail for the offset near the head
   whose short-time spectral content (a windowed FFT magnitude comparison) is closest to it —
   picking a spectrally similar splice point measurably reduces audible seams beyond what the
   crossfade alone can hide, versus splicing at an arbitrary cut.
3. **Crossfade-splice.** Apply the mixer's existing 250 ms equal-power crossfade at the chosen
   seam — this reuses `ChapterAssembler._tile_with_crossfade` unmodified; a generated asset is,
   from the mixer's point of view, exactly the same kind of loopable WAV a hand-authored one is.

**Spectral continuity check (validation, not just generation):** after splicing, compare the
FFT magnitude spectrum of a short window immediately before the seam to one immediately after.
If the spectral distance exceeds a threshold (the splice is audibly a "seam," not a
continuation), the generation is rejected and retried with a different seed, up to a bounded
retry count, before falling back a tier.

### Content-addressed cache

Every resolved asset — generated or bank-matched — is cached under a **literal** key:

```
cache_key = sha256(model_id + "|" + normalized_prompt + "|" + duration_ms + "|" + seed + "|" + generator_params_version)
```

This is intentionally exact (not fuzzy): the same model, the same prompt text, the same
requested duration, and the same seed always resolve to the same cached file, so re-running
the sound planner on an unchanged chapter never regenerates anything. Cache entries live in a
single, cross-project location — `.echodraft/cache/generated-audio/{cacheKey[:2]}/{cacheKey}/asset.wav`
plus a sibling `metadata.json` — alongside the existing `.echodraft/kokoro/` and
`.echodraft/local-ai/` roots (config var `ECHODRAFT_GENERATED_AUDIO_CACHE_ROOT`, default
`.echodraft/cache/generated-audio`), because Echodraft already runs one SQLite database and
one local install across all projects (`.echodraft/echodraft.db`,
`ECHODRAFT_ARTIFACT_ROOT=.echodraft/projects`) — an ambience bed generated for one book is
immediately reusable by any other project on the same machine.

This is distinct from (and complements) the **bed-signature** continuity match the planner
uses to decide "don't re-select a new bed for a contiguous same-environment run of scenes"
(above) — the bed signature governs *planning* decisions across a chapter; the content-address
key governs *asset* reuse across chapters and books. A coarser bed signature deliberately
collapses many distinct free-text prompts onto the same handful of generated beds — see the
cache-hit math in [Performance](#performance).

Each project's `AmbienceAssetRecord` row for a cached asset stores its own `id`/`project_id`
but points its `asset_path` straight at the shared cache file — never a per-project copy —
since the file is immutable once QA'd. An asset file is only eligible for garbage collection
once zero `ambience_assets` rows across the whole database reference its path.

### Loudness pre-normalization

Because generated clips can arrive at wildly different native loudness depending on model and
prompt, every asset — generated or bank — is loudness-measured and pre-normalized to a fixed
reference level (e.g., **-23 LUFS integrated**, a conservative "ambient bed" reference, well
below narration level) **before** it is ever stored as an `AmbienceAssetRecord`. This matters
because the mixer's per-mode gain ceilings (`_cue_gain` in `assembly.py`) operate on
`cue.gain_db`, not on the asset's own loudness — without pre-normalization, a hot generated
clip could sit far louder than the ceiling implies relative to a quiet uploaded WAV, even
though both cues declare the same `gain_db`. Pre-normalization makes "gain_db means the same
thing regardless of asset provenance" actually true. This reuses the same ffmpeg two-pass
`loudnorm` primitive `mastering.py` already uses for chapter mastering, just at a different
target level and applied to the standalone asset file instead of the assembled chapter.

### Automatic QA and regeneration-on-fail

Before an asset is accepted into the cache, it is run through automated checks, reusing and
extending the existing per-render QA machinery in `audio_analysis.py`
(`ReviewService._audio_rules`) rather than building a parallel system:

- **Clipping** — the same sample-at-full-scale ratio check already used for segment/chapter
  QA.
- **Silence** — an RMS-floor check; a near-silent generation almost always means a degenerate
  or failed model output, not "quiet ambience."
- **Tonal/artifact detection** — a spectral-flatness (Wiener entropy) measurement. Ambience
  beds should be broadband and noise-like; a low flatness score indicates energy is
  concentrated in a narrow band over time, i.e., the model produced a hummable tone or drone
  instead of texture — the known "melody/vocal leakage" failure mode of text-to-audio
  ambience prompts. This is the mechanical backstop for the "no music, no melody" negative
  prompt above.
- **Spectral continuity at the loop seam** — described above, specific to loopable ambience.

On any QA failure: retry generation with a re-rolled seed and a strengthened negative prompt,
bounded (default 3 attempts) — mirroring the existing "one retry on schema failure" convention
already used for LLM extraction calls in `local_llm.py`. After exhausting retries, cascade
down a tier (generative model → Tier-0 bank nearest match) rather than giving up; if even the
bank has no reasonable match, the scene is left with **no ambience bed** and a durable, low
severity `issue` is opened (category `sound_design`) — silence is always an acceptable
fallback, a wrong or broken asset is not.

## Automatic cue placement

Once an asset is resolved (cached, freshly generated, or bank-matched), the planner's
abstract placement becomes a concrete `AmbienceCueRecord`, written with `origin =
"auto_generated"` (new field, see [data model impact](#data-model-api-and-manifest-impact)).
Placement reuses the existing cue fields and existing mixer behavior exactly — no new mixing
logic is introduced by this document.

### Ambience cues

- **Start**: `start_ms = 0` relative to the scene's offset in the assembled timeline (a
  continued bed, per the planner's continuity rule, is placed once at the first scene of the
  run and simply loops through the following scenes rather than re-triggering).
- **End**: implicit — the cue's tiled/looped material runs to the scene boundary (or the end
  of the contiguous same-bed run); a `fade_out_ms` is applied at that boundary unless the next
  scene continues the same bed, in which case no fade is needed.
- **Fades**: default `fade_in_ms`/`fade_out_ms` of 800 ms (matching the existing scene-boundary
  pause), capped to at most a quarter of the scene's own duration so a very short scene never
  gets a fade longer than the scene itself.
- **Gain**: resolved from the mode's existing ceiling table in `ChapterAssembler._cue_gain` —
  ambience/music cap at **-18 dB** in `light_cinematic` and **-14 dB** in `dramatized`; the
  planner never requests a `gain_db` above the ceiling, but the mixer's `min(cue.gain_db,
  maximum)` clamp remains the actual enforcement point.
- **Ducking**: `true` by default — an automatically placed ambience cue always ducks under
  narration, using the existing static -6 dB / 50 ms ramp behavior.

### Music entry/exit rules

- **Chapter opening**: the cue starts at `start_ms = 0` of the chapter (before the room-tone
  head that mastering adds), and `fade_in_ms` is set to the duration of the scene's **first
  paragraph** — located via the chapter manifest's existing per-segment `timeline` entries
  (`{segmentId, sceneId, startMs, endMs}`, written by `ChapterAssembler._write_speech_stem`):
  the fade-in duration is `timeline[0].endMs - timeline[0].startMs`, capped to a maximum of
  ~6000 ms so a very long opening paragraph doesn't stretch the fade unreasonably.
- **Fade out before first dialogue, never under dialogue by default**: the cue's effective end
  is clipped to just before the `startMs` of the first `timeline` entry whose segment has
  `segment_type == "dialogue"` (the two possible `segment_type` values in the schema, per
  `structure_parsing.py`), minus a short lead-out (`fade_out_ms`, default 1500 ms). If a scene
  has no dialogue at all, the cue simply runs to the scene boundary and fades there instead.
  A future per-cue `allowUnderDialogue` override could relax this for advanced users, but the
  planner never sets it.
- **Emotional-peak underscore** (dramatized only) follows the same fade-in/out shape scaled to
  the scene's own paragraph/dialogue boundaries, and is subject to the "never overlaps an SFX
  cue" guardrail from the planner.

### SFX time-anchoring algorithm

Given a planned SFX event (`eventType`, `sentenceEvidence`, `confidence`) and its scene, the
algorithm locates a concrete millisecond offset in the assembled chapter timeline:

1. **Locate the segment.** Normalize whitespace/casing on both `sentenceEvidence` and each
   candidate segment's `normalized_text` within the scene. Try exact substring containment
   first (the LLM was asked for a verbatim-or-near-verbatim quote); if no segment contains it
   verbatim, fall back to token-overlap (Jaccard) scoring across the scene's segments and take
   the best match above a minimum threshold, tie-breaking by segment order. No match above
   threshold ⇒ the event is unanchorable and is skipped (`log_skip("no_timeline_anchor")`,
   per the planner pseudocode above) — an SFX cue is never guessed onto the wrong segment.
2. **Resolve the segment's timeline entry.** Look up that `segmentId` in the chapter's
   already-produced `timeline` list (`{segmentId, startMs, endMs}` — the same structure
   `ChapterAssembler` writes today and the manifest already carries). This is a real,
   already-implemented data source; the algorithm adds no new tracking to produce it.
3. **Approximate an intra-segment offset.** Echodraft has no forced word-level alignment
   today (the "alignment path" field named in the segment render manifest's payload list in
   [pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md) is aspirational,
   not implemented) — so the offset within the segment is a **heuristic**, not a measurement:
   `offset_ratio = char_index_of_matched_text / len(segment.normalized_text)`, and
   `anchor_ms = segment.startMs + round(offset_ratio * (segment.endMs - segment.startMs))`.
   This is honest about its precision: it places an SFX within roughly the right sentence, not
   at a word-perfect instant. If [tts-engine-strategy.md](../tts/tts-engine-strategy.md) ever
   adds real per-word alignment (e.g., via the existing optional `whisper_cpp` ASR path used
   for render QA), this step should be replaced with an exact word-timestamp lookup — that
   upgrade is called out as an open question below, not assumed.
4. **Guardrail checks** (no-SFX flag, budget, music-overlap) run against this resolved anchor
   before the cue is created, as shown in the planner pseudocode.

## Taste guardrails (machine-checked)

These are enforced in code, not left to prompt engineering or documentation:

| Guardrail | Enforcement point | Rule |
|---|---|---|
| Max concurrent layers | Sound planner (`overlaps_music_window`) + mixer | At most speech + 1 ambience + 1 of {music, sfx} active at any instant. An SFX event that would overlap an active music cue's window is skipped, never layered on top of it. |
| Gain ceilings per mode | `ChapterAssembler._cue_gain` (existing, unchanged) | `light_cinematic`: ambience/music ≤ -18 dB, SFX ≤ -14 dB. `dramatized`: ambience/music ≤ -14 dB, SFX ≤ -10 dB. The planner never requests above ceiling; the mixer clamps regardless. |
| Clean narration default preserved | Sound planner entry check | `speech_only` never invokes the planner; generative sound design only activates in `light_cinematic` and `dramatized`. |
| No-SFX segment flag respected | Sound planner, before spending SFX budget | An SFX anchor is only accepted if the anchored segment's resolved `DirectionProfile.noSfx` is `false`. This is the field's first real producer/consumer — see [Current state](#current-state-and-the-gap). |
| Per-chapter SFX budget | Sound planner | Default 2 (`light_cinematic`) / 5 (`dramatized`) SFX cues per chapter, project-configurable; excess events are logged and skipped, never silently exceeded. |
| One ambience bed per scene | Sound planner | Enforced structurally — the planner's per-scene loop calls `select_bed` at most once. |
| At most one opening + one peak music cue per chapter | Sound planner | `opening_music_placed` / `peak_music_placed` flags in the planner loop. |
| Ducking under narration | Mixer (existing, unchanged) | Auto-placed ambience/music cues default `ducking=true`, using the existing -6 dB / 50 ms ramp. |

## User control model

Nothing generated is final or hidden:

- **Regenerate.** Any auto-placed cue's asset can be regenerated with a different seed (same
  prompt) or a user-edited prompt, from the same Sound Design panel that already exists for
  manual cues.
- **Mute.** A cue can be muted without deleting it (a `muted` flag, analogous to the existing
  `no_sfx` per-cue suppression already implemented in the mixer) so a user can turn a cue back
  on later without losing its evidence trail.
- **Swap asset.** Point the cue at a different `AmbienceAssetRecord` — including a
  user-uploaded one via the existing `POST /sound-assets` path, which is untouched and remains
  fully supported as the override mechanism.
- **Upload replacement.** The manual upload path from [sound-design.md](sound-design.md)
  continues to work exactly as today; automatic generation and manual upload write to the same
  `ambience_assets` table and are interchangeable from the mixer's point of view.
- **Lock.** Once a user edits an auto-placed cue, it is marked `user_locked` (mirroring the
  existing `SceneRecord.user_locked` / speaker-attribution `userLocked` convention) so a
  chapter re-run of the sound planner never silently overwrites a human's decision.
- **Evidence trail.** Every automatically placed cue stores *why* it exists: the scene's
  atmosphere profile fields that drove the choice (for ambience/music) or the exact
  `sentenceEvidence` text (for SFX), plus the rule name that placed it (`"scene_ambience_bed"`,
  `"chapter_opening_music"`, `"emotional_peak_underscore"`, `"explicit_sound_event"`) — the
  same "show your work" pattern `speaker_attributions` evidence already uses. A "Why this
  sound?" affordance in the UI reads directly from this field, no new backend query needed.

## Data model, API, and manifest impact

All additions are backward-compatible: existing manually-created `AmbienceAssetRecord` /
`AmbienceCueRecord` rows are simply rows where the new fields hold their default
(`provenance="uploaded"`, `origin="user_created"`). Nothing here changes the mixing engine,
the manual upload endpoints, or the manual cue-creation endpoint.

### Atmosphere profile on the structure manifest and `scenes` table

`SceneRecord` already carries `parser_evidence_json` (Text, default `"{}"`) for structural
parser evidence. This design adds a sibling column following the same convention:

```python
atmosphere_profile_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
```

populated by the atmosphere-profile LLM call and mirrored into `structure_manifest.json`'s
per-scene payload (alongside the existing scene list, character candidates, and speaker
attribution confidence already documented in
[pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md)).

### New per-chapter manifest: `sound_plan_manifest.json`

A new manifest type, following the existing common envelope:

```json
{
  "manifestType": "sound_plan_manifest",
  "schemaVersion": "0.1.0",
  "projectId": "proj_001",
  "chapterId": "chap_014",
  "generatedAt": "2026-07-07T12:00:00Z",
  "status": "completed",
  "payload": {
    "renderMode": "light_cinematic",
    "atmosphereProfiles": { "scene_0041": { "...": "..." } },
    "plannedCues": [
      {
        "sceneId": "scene_0041",
        "kind": "ambience",
        "rule": "scene_ambience_bed",
        "bedSignature": ["tavern", "interior", "none", "night"],
        "continuedFromPreviousScene": false
      }
    ],
    "budgets": { "sfxUsed": 2, "sfxLimit": 2 },
    "skipped": [
      { "sceneId": "scene_0047", "eventType": "gunshot", "reason": "chapter_sfx_budget_exhausted" }
    ]
  },
  "diagnostics": []
}
```

This sits alongside `chapter_assembly_manifest.json` in the manifest list in
[pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md) — the sound plan
records *decisions*, the chapter assembly manifest (unchanged) records the *mixed output*.

### `AmbienceAssetRecord` — generated-asset provenance fields

New columns (all nullable except `provenance`, which already exists and simply gains new
valid values: `"uploaded"` (existing/default), `"generated"`, `"bank"`):

```python
model: Mapped[str | None] = mapped_column(Text)              # e.g. "stable-audio-open-1.0"
prompt: Mapped[str | None] = mapped_column(Text)              # normalized prompt text, or bank query
seed: Mapped[int | None] = mapped_column()
cache_key: Mapped[str | None] = mapped_column(String(64), index=True)
qa_status: Mapped[str] = mapped_column(String(32), nullable=False, default="n/a")  # passed|failed|regenerated|n/a
```

`license_note` (existing column) is populated from the Model Center catalog entry's
`license_summary` at generation time, so an asset's license travels with it even if the
catalog entry is later updated or removed.

### `AmbienceCueRecord` — auto-placement provenance fields

```python
origin: Mapped[str] = mapped_column(String(32), nullable=False, default="user_created")  # user_created|auto_generated
evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")            # rule name, atmosphere fields, sentence evidence
muted: Mapped[bool] = mapped_column(nullable=False, default=False)
user_locked: Mapped[bool] = mapped_column(nullable=False, default=False)                  # mirrors SceneRecord.user_locked
```

### `project_production_settings` — sound-design configuration

Following the existing `default_direction_json` convention (a flexible JSON blob rather than
many scalar columns):

```python
auto_sound_design_json: Mapped[str | None] = mapped_column(Text)
# { "enabled": true, "tier": "tier1_generative", "sfxBudget": {"light": 2, "dramatized": 5},
#   "allowOpeningMusic": true, "allowPeakMusic": true }
```

### API additions

- `POST /api/v1/projects/{projectId}/chapters/{chapterId}/sound-plan` — runs the atmosphere
  profile pass (if not already present for the chapter's scenes) and the planner, writes
  `sound_plan_manifest.json`, and materializes `AmbienceAssetRecord`/`AmbienceCueRecord` rows
  with `origin="auto_generated"`. Idempotent: re-running skips scenes whose profile/plan is
  unchanged and never touches `user_locked` cues.
- `POST /api/v1/projects/{projectId}/sound-assets/{assetId}/regenerate` — re-runs asset
  generation with a new seed or edited prompt, replacing the cue's asset reference (append-only
  history preserved via a new `AmbienceAssetRecord` row, matching the append-only render
  history convention used everywhere else in the pipeline).
- `PATCH /api/v1/projects/{projectId}/sound-cues/{cueId}` — extended to accept `muted`.
- Existing endpoints (`GET/POST /sound-assets`, `/sound-assets/from-path`, cue CRUD) are
  unchanged.

### Model Center catalog additions

New `model_catalog.yaml` entries, following the existing entry shape exactly
(`display_name`, `capability`, `provider`, `install_type`, `required`, `size_mb`,
`license_summary`, `description`):

```yaml
  procedural_sound_bank:
    display_name: Procedural Ambience & CC0 Sound Bank
    capability: ambience_bank
    provider: bundled
    install_type: bundled_asset
    required: true
    size_mb: 200
    license_summary: CC0 samples and project-authored DSP synthesis; no restrictions.
    description: Always-available ambience/SFX fallback tier; no network required.

  stable_audio_open:
    display_name: Stable Audio Open 1.0
    capability: audio_generation
    provider: stability_ai
    install_type: managed_download
    required: false
    size_mb: 5000
    license_summary: >-
      Stability AI Community License — free under a revenue threshold, commercial
      license required above it. Verify current terms before commercial distribution.
    description: Recommended local generative ambience/SFX/short-music model (Tier 1).

  audiocraft_audiogen:
    display_name: AudioCraft AudioGen (Meta)
    capability: sfx_generation
    provider: meta_audiocraft
    install_type: managed_download
    required: false
    status: non_commercial_only
    size_mb: 3500
    license_summary: >-
      CC-BY-NC 4.0 — non-commercial only. Do not use for a commercially distributed
      audiobook.
    description: Optional SFX generation model for personal/non-commercial projects.

  audiocraft_musicgen:
    display_name: AudioCraft MusicGen (Meta)
    capability: music_generation
    provider: meta_audiocraft
    install_type: managed_download
    required: false
    status: non_commercial_only
    size_mb: 3500
    license_summary: >-
      CC-BY-NC 4.0 — non-commercial only. Do not use for a commercially distributed
      audiobook.
    description: Optional music generation model for personal/non-commercial projects.

  tangoflux:
    display_name: TangoFlux (Declare Lab)
    capability: audio_generation
    provider: declare_lab
    install_type: managed_download
    required: false
    status: experimental
    size_mb: 3000
    license_summary: >-
      Verify exact checkpoint license before use; historically non-commercial-leaning.
      Not enabled by default.
    description: Fast flow-matching audio generator; bake-off candidate, not launch-qualified.

  ace_step:
    display_name: ACE-Step
    capability: music_generation
    provider: ace_studio_stepfun
    install_type: managed_download
    required: false
    status: experimental
    size_mb: 4000
    license_summary: >-
      Reported Apache-2.0 by the project; verify before relying on it commercially.
    description: Fast instrumental/vocal music generator; bake-off candidate.
```

`YuE` is deliberately **not** added to the catalog — it targets full-song generation with
vocals, the wrong grain for ambient underscore (see survey table); it can be reconsidered if
a future use case (e.g., an actual theme-song feature) needs it.

### Storage layout

```
.echodraft/
  echodraft.db                       # unchanged — single cross-project DB
  projects/{projectId}/...           # unchanged — per-project artifacts (segments, chapters)
  cache/
    generated-audio/{keyPrefix}/{cacheKey}/
      asset.wav
      metadata.json                  # model, prompt, seed, duration, license, qaStatus, createdAt
  local-ai/                          # unchanged — Model Center install state
  kokoro/managed-onnx-v1/            # unchanged — managed Kokoro runtime
```

No audio blob is ever stored in SQLite — the DB holds `asset_path`/`cache_key` only, per
constraint #7. The shared cache root is new; everything else is unchanged.

## Performance

- **Atmosphere-profile extraction is cheap and fully parallel.** It is a single
  schema-constrained call per scene against the same local model class already used for
  structure refinement (`qwen3:4b`-class, seconds per call). Because it has no cross-scene
  ordering dependency (unlike cast discovery/attribution), it should run across the full
  parallel window-worker pool described in
  [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md), immediately after
  scene boundaries are finalized — well before cast discovery or attribution need to be
  sequential about anything.
- **Asset generation is the expensive part and runs off the critical path.** Diffusion/flow-matching
  inference for a Tier 1+ model is tens of seconds per clip on consumer hardware. It runs on a
  dedicated **audio-gen worker pool** — a generalized version of the single resident-worker
  pattern `tts_worker.py` already uses for Kokoro, sized to available VRAM (commonly `N=1` on
  modest consumer GPUs, since these models are memory-hungry). Because the sound plan only
  needs atmosphere profiles — available immediately after structure extraction, long before
  the (currently sequential) TTS rendering of every segment finishes — asset generation for
  an entire book's scenes can run **overlapped with TTS rendering** rather than after it,
  so by the time chapter assembly runs, the needed assets are already cached and assembly's
  own cost is exactly what it is today.
- **Cache-hit math.** The content-addressed cache key is exact (model+prompt+duration+seed),
  but the *planner's* bed-signature collapses many scenes onto a small number of distinct
  prompts: a typical novel's scenes cluster into a modest number of coarse signatures
  (location category × interior/exterior × weather × time-of-day × mood bucket) — often on the
  order of a few dozen distinct beds for an entire book, even one with hundreds of scenes (a
  real measured run had 6,995 segments across 600+ scenes; most books do not have 600 distinct
  *environments*). Once those handful of beds are generated and QA'd once, every later scene
  sharing a signature is a cache hit, and every later *book* with a similar scene is also a
  cache hit, so steady-state marginal generation cost trends toward zero after the first few
  chapters — and the first few books — "warm" the shared cross-project cache.
- **No regression to the existing mixer or mastering cost.** Nothing in this design changes
  the numpy mixing, crossfade, ducking, or ffmpeg mastering cost documented in
  [sound-design.md](sound-design.md) — those already run in vectorized numpy and are not the
  bottleneck.

## Evaluation plan

Automated regression gate (CI-runnable, no model installed required for the Tier-0 path):

- Reuse `audio_analysis.py`'s existing clipping/silence checks plus the new spectral-flatness
  tonal check as an automated QA gate over the bundled CC0 bank and any checked-in reference
  fixtures for the procedural generators.
- A fixed regression corpus of representative scenes (a handful of chapters spanning literary
  fiction, thriller, fantasy, and historical genres) runs through the planner with each
  installed tier, asserting: budgets are respected, no cue exceeds its mode's gain ceiling, no
  SFX overlaps a music window, and every generated asset passes automated QA within the retry
  bound.

Human evaluation (required before promoting any Tier 1+ model from "experimental" to
"recommended"):

- **Blind A/B listening panel** comparing (a) clean narration, (b) `light_cinematic` with
  Tier-0 only, (c) the same chapters with the candidate generative tier, across the same
  regression corpus.
- Rubric, 1–5 scales unless noted:
  - *Distraction*: "Does the ambience/music pull attention away from the narration?" — pass
    bar: median ≤ 2.
  - *Appropriateness*: "Does it fit the scene's setting and mood?"
  - *Presence*: "Would you notice if this cue were silently removed?" — the target answer is
    "barely," not "no" (too weak to matter) and not "very much" (too loud/present).
  - *Artifacts*: binary yes/no + timestamp for any audible click, seam, tonal drone, or
    hallucinated voice/melody. Pass bar: zero blocking artifacts across the corpus.
- A tier only moves from Tier 3 (experimental) to Tier 1/2 (recommended) after clearing both
  the automated gate and this rubric — this is the "bake-off" referenced throughout the model
  survey.

## Migration path

1. **Ship Tier 0 first.** Procedural DSP + bundled CC0 bank requires no model dependency and
   immediately satisfies "not user-uploaded" for the common ambience cases — lowest risk,
   fastest path to the product mandate.
2. **Add atmosphere-profile extraction as an additive, optional structure-extraction sub-step.**
   Behind a flag, non-blocking: a failed or low-confidence profile call degrades to "no
   ambience for this scene," never blocks structure extraction, mirroring the existing "local
   LLM failure creates a warning issue, doesn't block the job" convention used by speaker
   attribution and direction inference.
3. **Add the deterministic sound planner and automatic cue placement**, writing to the
   existing `AmbienceCueRecord`/`AmbienceAssetRecord` tables via the new, purely additive
   columns above. The manual upload and manual cue-placement paths are completely untouched
   and remain the override mechanism throughout.
4. **Add Model Center catalog entries for Tier 1** (Stable Audio Open) behind explicit
   consent, and stand up the audio-gen worker pool and shared cache.
5. **Tier 2/3 entries ship as clearly-labeled experimental/non-commercial-flagged catalog
   entries** after their own bake-off, gated behind an explicit "experimental models" or
   "non-commercial use only" settings toggle — never silently promoted to default.
6. **Existing projects are unaffected.** A project with only manually uploaded assets and
   manually placed cues keeps working exactly as-is; a per-chapter "generate ambience" action
   becomes available without forcing a full project re-run, and running it never overwrites a
   `user_locked` cue.

## Risks and open questions

- **Licensing of model *outputs*, not just weights, is genuinely unsettled.** For CC-BY-NC
  checkpoints (AudioGen/MusicGen) it is not universally agreed whether the license encumbers
  only weight redistribution or also the generated audio itself. Echodraft's stance must be
  conservative — treat NC-model output as NC-restricted unless a specific license explicitly
  says otherwise — and the UI must surface this per-asset via the `model`/`license_note`
  provenance fields threaded through this design. This should be re-verified, not assumed,
  before any commercial-facing release.
- **Seed determinism is not guaranteed across hardware.** The same `(model, prompt, seed)`
  may not produce bit-identical output across different GPUs/CPU backends. The cache should be
  treated as an intra-install optimization (speed, not cross-machine byte-identical
  distribution) — a cache miss on a different machine is an acceptable outcome, not a bug.
- **CPU-only hardware may make Tier 1+ generation impractical** within any reasonable time
  budget. The mitigation already built into this design — Tier 0 fallback, plus background
  generation overlapped with TTS rendering rather than on the interactive critical path — 
  should keep the feature usable, but real-machine benchmarking is needed before claiming a
  time budget number.
- **Quality ceiling for unusual textual SFX events.** A model asked for a very specific or
  unusual sound (e.g., "the clockwork raven's wings creaking") may return something generic or
  wrong. Confidence gating, the strict SFX budget, and one-click mute/regenerate are the
  mitigations; this design does not claim perfect event-to-sound fidelity.
- **Voice/melody leakage in "ambience-only" generations** is a known failure mode of
  text-to-audio models and is only partially solved by negative prompting plus the
  spectral-flatness QA check — expect ongoing tuning of the flatness threshold against real
  generations during the bake-off, not a one-time fix.
- **SFX time-anchoring is heuristic, not word-aligned**, because no forced word-level alignment
  exists in the pipeline today (see the SFX anchoring algorithm above). If
  [tts-engine-strategy.md](../tts/tts-engine-strategy.md) or a future ASR-alignment pass adds
  real per-word timestamps, the anchoring step should be upgraded and this document revised —
  it is an open dependency, not a design flaw to work around indefinitely.
- **Where the audio-gen worker pool lives inside the broader job/orchestration architecture**
  (queue depth, GPU contention with TTS if TTS ever gains a GPU path, checkpoint/resume
  behavior) is owned by [target-architecture.md](../../architecture/target-architecture.md);
  this document assumes such a pool exists and is schedulable independently of the TTS render
  queue, but does not define the orchestration mechanism itself.
