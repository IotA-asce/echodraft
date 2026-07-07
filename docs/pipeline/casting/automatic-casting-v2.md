# Automatic Casting v2

See also: [character-bible.md](character-bible.md), [voice-bible-spec.md](voice-bible-spec.md), [speaker-attribution.md](speaker-attribution.md), [../../architecture/extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) (character profiles this doc consumes), [../tts/tts-engine-strategy.md](../tts/tts-engine-strategy.md) (voice synthesis mechanics behind the catalog), [../../architecture/pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md), [../../domain/domain-model.md](../../domain/domain-model.md)

## Purpose

Voice casting is currently a manual, per-character chore: a user creates voice profiles, opens each character record, reads a keyword-scored suggestion list, and clicks one — repeated for every named character and the narrator, in every project. For a 500-page novel with 100+ named characters this is not a UX inconvenience, it is a wall. This document specifies **automatic casting v2**: a pipeline stage that assigns a narrator voice and a distinct-as-possible character voice to every speaking character with zero required user input, while keeping every assignment inspectable, explainable, and freely overridable.

The product mandate this document implements (see the shared v2 brief): *"Voice assignment to characters and narrator must be fully automatic. User input only if they want to edit."*

## Goals

1. **Zero-touch default casting for 100% of books.** Running the pipeline on a manuscript with no casting-related input from the user must produce a fully voiced project: a narrator and, for every character with attributed dialogue, a character voice.
2. **Every character voiced.** No speaking character reaches chapter production without a resolved voice — either a dedicated catalog voice (majors), a pooled catalog voice with a distinguishing offset (minors), or an explicit, intentional fallback to the narrator voice (true walk-ons), never an unresolved/undefined state.
3. **Narrator auto-selected.** Point-of-view analysis and a style preset (with a sane zero-touch default) choose the narrator without requiring the user to browse a voice list first.
4. **Everything overridable afterward.** Auto-casting output is a starting point, not a lock-in: any assignment can be changed after the fact through the existing character/voice APIs, and doing so must not force a full project re-render (see [User override model](#user-override-model)).
5. **Deterministic and explainable.** The same manuscript + catalog state always produces the same casting; every decision carries a stored evidence trail answering "why this voice for this character."
6. **Respect the voice bible's do-not-cross rules** ([voice-bible-spec.md](voice-bible-spec.md)) as machine-checked constraints, not just prose guidance.
7. **Scale to 100+ character novels** on a small, fixed local voice catalog (today: Kokoro's ~50-odd voices) without degrading into "everyone sounds the same" or requiring the user to triage duplicates.

## Non-goals

- This document does not specify *how* a TTS engine renders emotion, whispering, or delivery — that is [tts-engine-strategy.md](../tts/tts-engine-strategy.md)'s scope. Casting selects *which voice*, not *how it is performed* per line.
- It does not specify ambience/music mixing (`docs/pipeline/assembly/`) or mastering loudness targets — out of scope for do-not-cross rule 4 ("ambience must not overpower speech clarity").
- It does not change the segment-render or chapter-assembly pipelines; it only changes how the `voiceProfileId` those pipelines already consume gets chosen.
- It does not require cloud services. Everything in this design — audition synthesis, acoustic feature extraction, LLM labeling, embedding computation, assignment solving — runs on the local engines and local LLM already present in the stack (Kokoro/Piper/XTTS, Ollama `qwen3:4b`).
- Full cross-book series continuity (§7) is specified only at a brief, phase-2 level; it is not part of the first implementation milestone.

## Current-state summary (and why it fails at scale)

Today's casting flow, as implemented:

- **Voice profiles are hand-created.** `VoiceProfileRecord` (`libs/db/src/echodraft_db/models.py:505`) stores only `name`, `backend`, `provider_voice_id`, and an optional `style_prompt` — no real metadata columns for gender, age, accent, timbre, or acoustic properties.
- **"Facets" are regex-guessed from the engine voice ID at read time**, not stored or measured. `_voice_facets()` (`apps/api/src/echodraft_api/main.py:346`) splits `provider_voice_id` into tokens and maps a hardcoded Kokoro ID-prefix table (`af`→`gender:feminine, accent:american`, `bm`→`gender:masculine, accent:british`, …) plus a keyword-token table (`"irish"`→`accent:irish`, `"young"`→`age:young`, …) onto whatever words happen to appear in the voice's ID or name string. There is no acoustic measurement anywhere in the code path — a voice literally named `af_bella` is labeled `gender:feminine` purely because its ID starts with `af`.
- **Assignment is a manual, per-character suggestion click.** `voice_suggestions()` (`main.py:288`) scores every project voice against a character's `traits_json` by casefold-substring matching against the voice's name/backend/ID/style-prompt/facets, with a small synonym table (`feminine`↔`female, woman, girl`, etc.). Score is `matched_traits / total_traits`, ties broken alphabetically. The user must open each character, read the ranked list, optionally audition, and click `assign-voice` (`POST /api/v1/characters/{characterId}/assign-voice`, `main.py:1347`). `CharacterVoiceAssignmentRecord` (`models.py:543`) enforces one voice per character with no history of *why* it was chosen.
- **The narrator is a single manual field.** `ProjectProductionSettingsRecord.narrator_voice_profile_id` (`models.py:515`) is set once, by hand, in project production settings; nothing in the codebase analyzes point of view or suggests a narrator voice.
- **There is no distinctiveness logic at all.** Two characters who talk to each other constantly can be — and regularly are — assigned acoustically similar voices, because the suggestion score only looks at trait-keyword overlap, never at how a candidate voice compares to voices already chosen for other characters.

**Why this fails at scale:** a 500-page novel routinely surfaces 100+ named characters through cast discovery (a real measured run produced 601 cast candidates before dedupe — see the extraction pipeline research). Clicking through a suggestion list 100+ times, per project, with a scoring function that cannot tell two feminine, young, American-accented characters apart, is not a workflow a user will tolerate, and even when they do, the underlying facets are guesses about an ID string, not the voice itself. The manual model was adequate for a handful of principal characters; it does not scale to "any book," which is the actual product goal.

## Voice catalog v2

### What and why

The core fix is to stop guessing metadata from ID strings and instead maintain a **real, measured voice catalog**: one row per usable voice, populated once from the voice's own audio, not its filename. This catalog is the substrate every later matching/assignment step reads from.

### Schema

```json
{
  "id": "vcat_kokoro_af_bella_v1",
  "engine": "kokoro",
  "engineVersion": "managed-onnx-v1",
  "engineVoiceId": "af_bella",
  "synthesisKind": "fixed",
  "gender": "feminine",
  "ageRange": "young_adult",
  "accent": "american",
  "locale": "en-US",
  "timbre": ["warm", "breathy", "bright"],
  "energyDefault": "medium",
  "acoustics": {
    "pitchMedianHz": 211.4,
    "pitchRangeHz": [162.0, 318.5],
    "jitterPercent": 1.1,
    "shimmerPercent": 3.4,
    "tempoWpmDefault": 164,
    "spectralBrightness": 0.61
  },
  "embedding": {
    "model": "local-speaker-embed-v1",
    "vectorPath": "voice_catalog/kokoro/af_bella/embedding.npy",
    "dims": 192
  },
  "samplePaths": {
    "auditionWav": "voice_catalog/kokoro/af_bella/audition.wav",
    "waveformPreviewPng": "voice_catalog/kokoro/af_bella/waveform.png"
  },
  "license": {
    "source": "kokoro-82m",
    "type": "apache-2.0",
    "commercialUse": true,
    "attributionRequired": false,
    "consentRecordId": null
  },
  "labeledBy": {
    "method": "llm_from_acoustic_features",
    "model": "qwen3:4b",
    "llmRunId": "llmrun_8f2c...",
    "humanReviewed": false
  },
  "schemaVersion": "0.1.0",
  "createdAt": "2026-07-01T00:00:00Z"
}
```

Field notes:

| Field | Meaning | Source |
|---|---|---|
| `gender`, `ageRange`, `accent`, `locale` | Categorical facets used as hard/soft matching constraints | LLM label from acoustic features + engine metadata |
| `timbre` | Free-vocabulary descriptors (warm, gravelly, bright, nasal, raspy, authoritative, breathy, …), shared vocabulary with character `speaking_style_json` terms | LLM label |
| `acoustics.*` | Numeric, directly measured from the audition audio | Signal-processing feature extraction (no LLM) |
| `embedding` | Fixed-length speaker-embedding vector for distinctiveness scoring | Local embedding model, optional — degrade gracefully to `acoustics`-only distance if unavailable |
| `samplePaths` | Filesystem paths only — **never** raw audio in the DB row (constraint: no audio blobs in a relational DB) | Audition synthesis step |
| `license` | Whether the voice may be used/distributed, and whether cloning consent exists | Engine packaging metadata / consent flow |
| `labeledBy` | Provenance of the categorical labels, so a human curator knows what to spot-check | Audition pipeline |

### How fixed-voice engine entries are produced (Kokoro, Piper)

A **one-time automated audition pass** per installed engine, triggered from Model Center after the engine finishes installing (or on demand via `POST /api/v1/voice-catalog/audition-jobs`), not per project:

```text
for engine_voice_id in engine.list_native_voices():
    # 1. Synthesize a standard, phonetically-varied audition paragraph
    #    (~120 words; includes a statement, a question, an exclamation,
    #    and a short quoted aside, so pitch range and prosody are exercised)
    wav_path = engine.synthesize(AUDITION_PARAGRAPH, engine_voice_id)

    # 2. Extract acoustic features directly from the audio — no LLM involved
    pitch = extract_pitch_track(wav_path)          # e.g. autocorrelation / Praat-style tracker
    features = AcousticFeatures(
        pitch_median_hz   = median(pitch.voiced_frames),
        pitch_range_hz    = (p10(pitch.voiced_frames), p90(pitch.voiced_frames)),
        jitter_percent     = jitter(pitch.voiced_frames),
        shimmer_percent    = shimmer(wav_path),
        tempo_wpm          = word_count(AUDITION_PARAGRAPH) / duration_minutes(wav_path),
        spectral_brightness= spectral_centroid_ratio(wav_path),
    )
    embedding = speaker_embedding_model.encode(wav_path)   # optional, if a local model is installed

    # 3. One LLM labeling call per voice — features in, categorical labels out
    #    (the local LLM has no audio capability, so it never hears the voice;
    #    it reasons over the numeric features + known engine metadata)
    labels = ollama_call(
        model="qwen3:4b",
        schema=VoiceLabelSchema,               # gender, ageRange, accent(optional), timbre[], energyDefault
        prompt=render_labeling_prompt(engine_voice_id, features),
        temperature=0,
    )

    # 4. Persist one voice_catalog_entries row + sample WAV + embedding file
    catalog.upsert(engine, engine_voice_id, features, embedding, labels, sample_paths)
```

This is a fixed cost paid once per engine install (Kokoro today: ~50 voices, a few minutes total), not per project and not per book. It is idempotent and keyed by `(engine, engineVersion, engineVoiceId)`; a re-run only fires when the engine version changes (mirrors the existing Model Center install/verify pattern in `local_ai/service.py`).

Why an LLM call at all, given the features are already numeric: mapping "pitch median 211Hz, jitter 1.1%, tempo 164 WPM, spectral brightness 0.61" to human-usable labels like `ageRange: young_adult` and `timbre: [warm, breathy, bright]` is a categorization task the LLM already does well and consistently, and doing it once per catalog voice (tens of calls) is a negligible cost compared to the hundreds–thousands of sequential LLM calls the extraction pipeline already makes per book. Labels are marked `humanReviewed: false` until a curator screen (or a v1 skip) confirms them, and are treated as **preferred**-tier evidence in matching (§ below), not ground truth — see [Risks](#risks--open-questions).

### How cloning/synthesis engine entries are produced (virtual catalog)

Fixed-voice engines have an enumerable voice list; cloning and parametric synthesis engines do not — the "catalog" for those engines is a **continuous space**, not a fixed table. Full mechanics belong to [tts-engine-strategy.md](../tts/tts-engine-strategy.md) §"Character voice synthesis"; the casting-relevant contract is:

- **Cloned voices** (e.g., XTTS-v2 given a reference sample): each licensed reference sample the user or a bundled library provides becomes a *materialized* catalog entry structurally identical to a fixed-voice entry (`synthesisKind: "cloned"`), plus a `referenceAudioPath` and a `consentRecordId` that must be present before it is eligible for auto-cast (do-not-cross rule extension — see `license` handling below). The one-time audition pass runs against the *clone output*, exactly like a fixed voice, so the same acoustic-feature/LLM-labeling pipeline applies unmodified.
- **Parametric/zero-shot synthesis** (target facets → a synthesis seed or embedding point, no reference audio): the catalog entry stores `synthesisKind: "parametric"`, a deterministic `seed`, and the *target* facet vector used to steer synthesis, instead of a fixed `engineVoiceId`. Casting treats it exactly like any other catalog row for matching purposes; only the TTS layer needs to know it must synthesize-then-render rather than pick a pre-existing voice.

This keeps the casting algorithm identical regardless of which kind of engine backs a catalog entry — casting always operates on `voice_catalog_entries` rows with the schema above.

## Character profile → casting requirements

### What feeds this step

Cast discovery / speaker attribution already produce, per character (`CharacterRecord`, `models.py:482`, and [character-bible.md](character-bible.md)):

- `traits_json` — conservative, evidence-backed trait tokens (`role:captain`, `age:young`, `accent:irish`, `gender:feminine`, …)
- `speaking_style_json`, `relationships_json`
- `role_type` and `confidence`
- attributed dialogue via `speaker_attributions` rows (`SpeakerAttributionRecord`, `models.py:550`) linked by `character_id`, from which dialogue volume and scene co-occurrence are derived

None of this is new data to collect — it is the exact character-profile surface [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md) hands off. What is new is a deterministic transform from that profile into a **casting spec**: the requirements a voice must satisfy.

### Casting spec schema

```json
{
  "characterId": "char_042",
  "requiredFacets": {"gender": "feminine"},
  "preferredFacets": {"age": "elder", "accent": "irish"},
  "timbrePreference": ["warm", "raspy"],
  "prominenceClass": "major",
  "dialogueWordCount": 4820,
  "dialogueSegmentCount": 96,
  "sceneCoOccurrence": ["char_003", "char_011"],
  "confidence": 0.82,
  "evidenceRefs": ["trait:gender:feminine#mention_ledger:118", "trait:accent:irish#mention_ledger:204"]
}
```

### Algorithm: `derive_casting_spec(character, mentions, attributions)`

```text
function derive_casting_spec(character, mention_ledger, attributions):
    traits = parse_traits(character.traits_json)          # e.g. {"gender": "feminine", "accent": "irish", ...}

    # 1. Split traits into required (hard) vs preferred (soft).
    #    Only gender and an explicitly stated age band are ever "required":
    #    a wrong-gender voice is the single most jarring mismatch a listener
    #    notices; everything else is a preference, not a constraint.
    required = {}
    preferred = {}
    for key, value in traits.items():
        if key in ("gender", "age") and trait_support_count(mention_ledger, character, key) >= MIN_SUPPORT:
            required[key] = value
        else:
            preferred[key] = value

    # 2. Derive timbre preference from role + speaking-style vocabulary,
    #    mapped onto the same descriptor vocabulary the voice catalog uses.
    timbre = set()
    timbre |= ROLE_TIMBRE_DEFAULTS.get(traits.get("role"), set())      # e.g. role:captain -> {"authoritative"}
    for style_term in character.speaking_style_json:
        timbre |= STYLE_TO_TIMBRE_SYNONYMS.get(normalize(style_term), set())

    # 3. Compute dialogue volume from approved speaker_attributions rows.
    dialogue_segments = attributions.for_character(character.id, status="approved")
    word_count = sum(word_count(seg.text) for seg in dialogue_segments)

    # 4. Prominence class from word-count percentile within this project's cast.
    prominence = classify_prominence(word_count, project_word_count_distribution)
    #   major   : top 15% by dialogue word count, or >= 1000 words
    #   minor   : any approved dialogue below the major threshold
    #   walk_on : zero attributed dialogue lines (mention-only character)

    # 5. Scene co-occurrence: characters who share >=1 scene AND both have
    #    attributed dialogue in that scene are "conversation partners" —
    #    the set that must sound maximally distinct from this character.
    co_occurrence = conversation_partners(character.id, attributions)

    return CastingSpec(
        character_id=character.id,
        required_facets=required,
        preferred_facets=preferred,
        timbre_preference=sorted(timbre),
        prominence_class=prominence,
        dialogue_word_count=word_count,
        scene_co_occurrence=co_occurrence,
        confidence=character.confidence,
        evidence_refs=trait_provenance(mention_ledger, character, required, preferred),
    )
```

`ROLE_TIMBRE_DEFAULTS` and `STYLE_TO_TIMBRE_SYNONYMS` are small, hand-curated lookup tables (comparable in spirit to the existing `_voice_matches_trait` synonym table in `main.py:330`) — the only place casting quality logic depends on a manually maintained vocabulary, and it is intentionally small and inspectable.

## Automatic assignment algorithm

This is the core of the doc: given every character's casting spec and the voice catalog, produce a complete, deterministic assignment.

### Step 0 — Narrator selection (runs first, always)

The narrator is chosen before any character, because the narrator voice is then a hard exclusion for every character assignment that follows (do-not-cross rule 1).

```text
function select_narrator(book_pov, style_preset, catalog):
    if book_pov == "first_person":
        pov_character_spec = casting_spec_of(book_pov.narrating_character)
        # Narrator reads as a natural extension of the narrating character's
        # own voice register, but must still be acoustically distinct from
        # that character's own dialogue-voice assignment (a first-person
        # narrator quoting their own remembered dialogue should not sound
        # identical to their in-scene speaking voice).
        target = pov_character_spec.preferred_facets | {"timbre": pov_character_spec.timbre_preference}
        exclude = {pov_character_spec.character_id}   # resolved after character casting, see note below
    else:  # third_person or unknown
        preset = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["warm_neutral"])
        target = preset.target_facets   # default: {timbre: ["warm", "clear"], energy: "medium"}
        exclude = {}

    candidates = [v for v in catalog if v.license.commercial_use and not v.reserved]
    scored = [(score_voice_against_target(v, target), v) for v in candidates]
    return argmax(scored, tie_break=lambda v: (v.id))   # deterministic tie-break, see Determinism below
```

- **Point-of-view detection** comes from the extraction pipeline's narrative-voice analysis ([extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)); as a cheap, independent sanity fallback, casting also computes the first-person-pronoun ratio across `narration`-type segments and flags a mismatch (as a `casting` review issue) if it disagrees strongly with the pipeline's classification, so a bad POV call doesn't silently propagate into narrator selection.
- **Style presets** (`warm_neutral` default, plus `brisk`, `literary`, `theatrical`, `protagonist_pov`) are an optional, one-time project setting a user may set up front — never required. Each preset is just a target facet/timbre vector fed into the same scoring function used everywhere else.
- The chosen narrator voice is recorded and immediately **reserved**: removed from the assignable pool for every subsequent character (§ Consistency rules, rule 1).

### Step 1 — Prominence ordering

All characters are ranked by `dialogueWordCount` descending and processed **majors → minors → walk-ons**. Majors get first pick of the catalog while it is least depleted, since they are the assignments a listener will notice most. Walk-ons (zero attributed dialogue — mention-only characters) do not require a catalog voice at all: the existing production voice-resolution order already falls back to the narrator voice when a character has no linked voice (see [speaker-attribution.md](speaker-attribution.md) "Production Voice Resolution"), which is exactly the intended, tasteful behavior for a background character with a single unspoken mention — so auto-casting deliberately **skips** walk-ons rather than spending catalog voices on them, unless a user promotes one later.

### Step 2 — Scoring: `score(voice, character, already_assigned)`

```text
score(voice, character, already_assigned) =
      W_FACET   * facet_match(voice, character.required_facets, character.preferred_facets)
    + W_TIMBRE  * timbre_match(voice, character.timbre_preference)
    + W_SERIES  * series_continuity_bonus(voice, character)      # see §7, 0 until series linking exists
    - W_REPEAT  * repeat_voice_penalty(voice, character.prominence_class, already_assigned)
    - W_DISTINCT* distinctiveness_penalty(voice, character, already_assigned)
```

```text
function facet_match(voice, required, preferred):
    for key, value in required.items():
        if voice.facet(key) not in (value, "unknown"):
            return -INF                      # hard fail: never assign a wrong-gender voice, for example
    score = 0
    for key, value in preferred.items():
        score += MATCH_WEIGHT if voice.facet(key) == value else 0
    return score

function timbre_match(voice, preferred_timbre):
    if not preferred_timbre:
        return NEUTRAL
    return jaccard_overlap(voice.timbre, preferred_timbre)          # or cosine sim if a timbre embedding exists

function repeat_voice_penalty(voice, prominence_class, already_assigned):
    reused_by = [c for c, v in already_assigned.items() if v.id == voice.id]
    if not reused_by:
        return 0
    if prominence_class == "major":
        return LARGE_PENALTY               # majors avoid reuse whenever the catalog has an alternative
    return SMALL_PENALTY                    # minors are allowed, even expected, to share a pool

function distinctiveness_penalty(voice, character, already_assigned):
    penalty = 0
    for partner_id in character.scene_co_occurrence:
        if partner_id in already_assigned:
            partner_voice = already_assigned[partner_id]
            distance = feature_distance(voice, partner_voice)   # normalized pitch delta + embedding cosine distance
            if distance < DISTINCT_THRESHOLD:
                penalty += (DISTINCT_THRESHOLD - distance)       # only penalize voices that are too close
    return penalty
```

The `distinctiveness_penalty` term is the direct implementation of "characters who talk to each other need maximally distinct voices": it only fires between characters who actually appear in dialogue together (`scene_co_occurrence`, § above), not between every pair of assigned voices project-wide — two characters who never share a scene can safely sound similar, but two who argue in the same scene must not.

### Step 3 — Constraint-solving assignment

Two complementary strategies, chosen by cast size:

**Majors — Hungarian-style optimal assignment.** Build a cost matrix `characters (majors) × available voices` where `cost = -score(voice, character, already_assigned)` and hard-constraint violations are `+INF`. Solve with a standard assignment algorithm (e.g. `scipy.optimize.linear_sum_assignment`) for a globally optimal one-to-one mapping. At the scale this needs to handle (majors are, by definition, a small top slice of the cast — realistically under ~40 even in a sprawling ensemble novel), an `O(n³)` solve completes in well under a second, and it strictly dominates any greedy strategy because scene co-occurrence penalties are inherently a joint (not incremental) optimization — a purely greedy pick order can lock in a locally-good but globally-poor arrangement.

**Minors and pooled walk-on promotions — greedy-with-backtracking over a shared pool.** Minors do not need one-to-one uniqueness (do-not-cross rule 2 explicitly allows minor voice sharing), so they are assigned greedily in prominence order against the *remaining* catalog treated as a reusable pool:

```text
function assign_minors(minors, remaining_catalog, already_assigned):
    for character in sorted(minors, key=lambda c: (-c.dialogue_word_count, c.character_id)):
        candidates = [v for v in remaining_catalog if not violates_hard_constraints(v, character)]
        if not candidates:
            candidates = relax_soft_constraints(remaining_catalog, character)   # widen accent/age before giving up
        best = argmax(candidates, key=lambda v: score(v, character, already_assigned),
                      tie_break=lambda v: v.id)
        already_assigned[character.character_id] = apply_pool_offset(best, character, already_assigned)
    return already_assigned

function apply_pool_offset(voice, character, already_assigned):
    # When multiple minors share one catalog voice, give each a small,
    # deterministic tempo/pace offset (the only lever actually wired to
    # TTS engines today — see tts-engine-strategy.md) so they are not
    # byte-identical in delivery even though they share a base voice.
    siblings = [c for c, v in already_assigned.items() if v.id == voice.id]
    offset_index = len(siblings)
    return PooledVoiceAssignment(base=voice, pace_offset=POOL_PACE_OFFSETS[offset_index % len(POOL_PACE_OFFSETS)])
```

Both strategies share one bounded backtrack: if committing to a character's argmax pick would leave a later, still-unassigned major with **zero** valid remaining voices (checked by a cheap one-step lookahead over remaining hard-constraint-satisfying candidates), the solver backtracks to that character's next-best candidate instead, up to a small fixed depth (e.g. 3) to keep the whole pass roughly linear even on a 100+ character cast.

Note on the pooling offset: today only *pace* (Kokoro `--speed`, Piper `--length-scale`) is actually wired from `DirectionProfile` into any engine — pitch/formant shifting is not a rendering capability yet. Pooling therefore differentiates minors by pace/cadence, not pitch, until [tts-engine-strategy.md](../tts/tts-engine-strategy.md) either wires richer per-line acoustic control or a local pitch-shift DSP step is added to the assembly stage.

### Determinism and evidence

- **Determinism:** identical `(character profiles, catalog state, algorithm version)` inputs always produce identical output. All sorts use stable secondary keys (`characterId`, `voiceCatalogEntryId`); any place a choice must be made among true score ties uses a seeded RNG, seeded from `sha256(projectId + characterId)` truncated to an integer — never wall-clock time or set/dict iteration order. This guarantees re-running auto-cast on an unchanged project (or an unrelated part of a larger one) never silently reshuffles voices someone has already reviewed.
- **Evidence trail:** every assignment writes a `casting_decisions` row (§ Data model) capturing the top-3 scored candidates with their component scores, which hard constraints applied, which required/preferred facets matched or missed, which co-occurrence conflicts were avoided (or accepted, if the catalog forced a compromise), the `algorithmVersion`, and the `catalogVersion` used — the same "durable diagnostic evidence, never discarded" pattern already used for `speaker_attributions.evidence_json` and structure parser warnings.

## Consistency rules / voice-bible enforcement

[voice-bible-spec.md](voice-bible-spec.md) states its do-not-cross rules as editorial prose. Automatic casting turns each into a machine-checked constraint:

| Voice-bible rule | Machine check |
|---|---|
| Narrator voice must never be assigned to non-narrator characters unless explicitly approved. | The reserved narrator `voiceCatalogEntryId` is removed from the assignable pool before Step 1 runs (hard `-INF` constraint). A manual `assign-voice` call that targets the narrator's voice is rejected with `422` unless the request sets `allowNarratorReuse: true`. |
| Minor characters may share voices; major characters should not if avoidable. | `repeat_voice_penalty` is large for `prominenceClass: major` and small for `minor` (§ scoring). A post-assignment validator raises a `casting_quality` issue (severity `warning`) if two majors share a voice **and** an unused, hard-constraint-satisfying voice existed at assignment time — i.e., only when the collision was actually avoidable. |
| Comedic delivery must not break scene tone. | Out of scope for voice *selection*; casting only guards against picking a catalog voice whose stored `timbre`/`energyDefault` actively contradicts a character's tone traits (e.g. a `traits: ["tone:grim"]` character should not default to a `timbre: ["playful", "bright"]` voice) via the `timbre_match` term. Per-line comedic delivery is a direction/TTS concern — see [tts-engine-strategy.md](../tts/tts-engine-strategy.md). |
| Ambience and performance intensity must not overpower speech clarity. | Not a casting concern — assembly/mastering (`docs/pipeline/assembly/`) owns this; explicitly out of scope here. |
| Voice changes after chapter approval require stale-state handling and QA rerun. | Already implemented at the render layer: the segment render cache key includes the resolved voice profile (`rendering.py`), so any voice change — manual or auto-cast — invalidates only the affected segments' cached renders. Auto-casting **must** write through the same `assign-voice` path so this invalidation keeps firing; it must never write `character_voice_assignments` directly. |
| *(new, not in the original list)* Characters who converse need maximally distinct voices. | The `distinctiveness_penalty` scoring term (§ Step 2) plus a standing `castingQualityCheck`: for every scene with ≥2 speaking characters, compute pairwise `feature_distance` between their assigned voices and raise a `casting_distinctiveness` issue (severity `warning`) for any pair below `DISTINCT_THRESHOLD`. |

## Series/cross-book continuity (brief)

Echodraft projects are currently independent; a character in book 2 of a series has no link to "the same" character's voice chosen in book 1. A minimal, phase-2-scoped design:

- Add a series-scoped identity key — either a `seriesId` grouping on `projects` plus a normalized `canonicalCharacterKey` (name-based, reusing the existing shortlist-first dedupe approach from [character-bible.md](character-bible.md) but scoped *across* projects instead of within one), or a lightweight `series_character_voice_links` table keyed `(seriesId, canonicalCharacterKey) → voiceCatalogEntryId`.
- Cross-project character matching is fuzzy by nature (name variants, spelling) and must never silently merge two different projects' characters — the first match in a new book requires explicit user confirmation, exactly like same-project possible-duplicate review; only confirmed links feed future auto-cast runs.
- Once linked, a previously-used voice becomes a **preference**, not a hard constraint, inside the score function: `series_continuity_bonus` adds a large positive weight for the previously-used catalog voice, but that voice can still lose to a hard constraint in the new book (e.g., it happens to be needed as book 2's reserved narrator voice, or the character's traits were corrected between books).
- This is explicitly deferred past the first implementation milestone; §7 exists so the data model (§ below) does not need a breaking change when it is built.

## User override model

- Auto-casting is not a separate mutation path — it calls the same `assign-voice` / narrator-setting endpoints a human would, so every downstream mechanism (render invalidation, manifest updates, evidence) already works unmodified.
- `CharacterVoiceAssignmentRecord` (and the new narrator equivalent) gains a `user_locked` / `locked_reason` pair, matching the pattern already used on `CharacterRecord.user_locked`, `SpeakerAttributionRecord.user_locked`, and `SegmentDirectionRecord.user_locked`. Locking a character's voice or the narrator voice removes that voice from the assignable pool for everyone else — a locked assignment is treated exactly like the reserved narrator voice for constraint purposes.
- **Overriding invalidates only the affected segments.** Because the render fingerprint already includes the resolved voice profile, changing one character's voice makes only that character's approved-attribution segments' cached renders stale; the narrator's segments and every other character's segments are untouched. No new invalidation logic is needed — this is the existing patchability guarantee (append-only `SegmentRenderRecord`, re-render-on-demand) applied unchanged.
- **Re-running auto-cast respects locks.** A rerun (new chapters added, Character Bible corrected, catalog updated) treats every `user_locked` assignment — including the narrator — as fixed, non-reassignable state and removes its voice from the pool, then only re-scores and reassigns unlocked characters.
- **Never silently rewrite a project a human has already reviewed.** If a project has *any* existing `character_voice_assignments` rows without a `casting_decision_id` (i.e., pre-auto-cast, hand-assigned), the first auto-cast run treats them as locked-by-default rather than overwriting them, and produces a **proposal diff** (`GET /api/v1/projects/{projectId}/casting/proposal`) for anything it would change, which the user applies explicitly. On a project that has never been touched by a human, the zero-touch default applies directly — proposal and apply collapse into one automatic step, consistent with Goal 1.

## Data model & API impact

New tables:

- **`voice_catalog_entries`** — `id, engine, engine_version, engine_voice_id, synthesis_kind, gender, age_range, accent, locale, timbre_json, energy_default, pitch_median_hz, pitch_range_json, jitter_percent, shimmer_percent, tempo_wpm, spectral_brightness, embedding_path, sample_paths_json, license_json, labeled_by_json, reference_audio_path, consent_record_id, project_id (nullable — null for globally shared engine voices, set for a user-supplied cloning reference), created_at, schema_version`. Sample/embedding paths only — no audio blobs in the DB, matching the project's filesystem-artifact convention.
- **`casting_decisions`** — `id, project_id, character_id (nullable for the narrator row), role ('narrator'|'character'), voice_catalog_entry_id, prominence_class, score, candidate_scores_json, evidence_json, algorithm_version, catalog_version, user_locked, locked_reason, superseded_by_id, created_at`. Kept append-only (superseding via `superseded_by_id` rather than update-in-place) so a rerun's reasoning stays inspectable — the same evidence-preservation principle used for segment/chapter render history.

Changed tables:

- `character_voice_assignments` (`models.py:543`) gains `user_locked`, `locked_reason`, `casting_decision_id` — kept as the thin, denormalized "what a project currently uses" read path the frontend already queries, while `casting_decisions` becomes the source of truth for *why*.
- `project_production_settings` (`models.py:515`) gains `narrator_casting_decision_id`, `casting_style_preset` (`warm_neutral` default), and `auto_cast_enabled` (default `true` for new projects).
- `voice_profiles` (`models.py:505`) gains an optional `voice_catalog_entry_id` so a project-local voice binding can point at real measured metadata instead of `_voice_facets()`'s regex guess. `_voice_facets()` and the keyword-overlap scoring inside `voice_suggestions()` (`main.py:288-385`) are superseded by catalog lookups and the scoring function in this doc, and kept only as a fallback for voices with no catalog entry yet (e.g. a hand-uploaded custom reference not yet audited).

New/changed endpoints:

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/projects/{projectId}/casting/auto-run` | Runs full automatic casting (narrator + every unlocked character); returns a `Job` (same job-runner pattern as `structure.extract`). |
| `GET /api/v1/projects/{projectId}/casting/proposal` | Preview the assignment a rerun would make, as a diff against current state, without applying it. |
| `POST /api/v1/projects/{projectId}/casting/proposal/{proposalId}/apply` | Apply some or all of a previewed proposal. |
| `GET /api/v1/voice-catalog` | List catalog entries; filterable by `engine`, `gender`, `ageRange`, `accent`, `synthesisKind`. |
| `POST /api/v1/voice-catalog/audition-jobs` | Kick off the one-time audition pass for an installed engine (invoked by Model Center after install, or manually). |
| `GET /api/v1/characters/{characterId}/casting-decision` | Superset of today's `GET /api/v1/characters/{characterId}/voice-suggestions`: returns the chosen voice plus full scored evidence and ranked alternatives, so the existing "pick a different suggestion" UI keeps working unmodified. |
| `POST /api/v1/characters/{characterId}/assign-voice` (extended) | Accepts new `lockAssignment: bool` and `allowNarratorReuse: bool` fields. |

`casting_manifest.json` (already defined in [pipeline-manifest-spec.md](../../architecture/pipeline-manifest-spec.md)) payload gains: `catalogVersion`, `algorithmVersion`, `narratorSelection` (POV analysis result, chosen preset, evidence), per-assignment evidence blocks, and an unresolved/low-confidence casting issues list — using the same durable `issues` review-queue pattern (category `casting`, severities `info`/`warning`) the rest of the pipeline already uses, rather than inventing a new mechanism.

## Quality evaluation

- **Distinctiveness metrics:** for every scene with ≥2 speaking characters, compute pairwise `feature_distance` (normalized pitch-median delta + embedding cosine distance where available) between assigned voices. Report project-level "minimum pairwise distinctiveness among conversation partners" and "% of conversational pairs below `DISTINCT_THRESHOLD`" — both writable into the existing structure/casting quality summary the dashboard already surfaces.
- **Coverage metrics:** % of speaking characters with a resolved voice (target 100%), % of majors with a voice unique among other majors (target 100%), % of assignments that landed in a shared minor pool vs. a dedicated voice (informational, expected to rise as cast size exceeds catalog size).
- **Blind A/B checklist** (manual, local, borrowing the "Sunday Suspense yardstick" framing from `docs/product/quality-benchmark.md`): render a fixed multi-character scene, shuffle the voice↔character label mapping for a reviewer, and confirm the reviewer can identify who is speaking from audio alone, without the transcript, for every major-character pair in that scene.
- **Regression gate on `algorithmVersion` bumps:** re-run the audition/labeling pass plus a fixed benchmark project's full casting pass, and require the stored distinctiveness/coverage metrics not to regress versus the previous algorithm version before shipping the bump.

## Migration path

1. Add `voice_catalog_entries` + a migration; backfill it with a one-time audition job against the currently-installed engine (Kokoro, the only default-installed engine today). This alone replaces `_voice_facets()`'s guessed output with measured/labeled data for existing voices without changing `VoiceProfile.facets`'s API shape (still `list[str]` of `namespace:value` tokens), so the current frontend voice-suggestion UI keeps working unmodified during rollout.
2. Add `casting_decisions` plus the `derive_casting_spec` → score → assign services described above. Ship behind `auto_cast_enabled` (default `true` for new projects; existing projects with hand-assigned voices are prompted opt-in, since retroactively applying auto-cast must never silently clobber a human's prior decisions — see the override model's locked-by-default rule).
3. Auto-chain `casting.auto-run` after Character Bible + speaker attribution reach a stable state, the same way cast discovery already auto-chains after structure refinement (see [character-bible.md](character-bible.md): "Structure extraction automatically runs Cast Discovery after refined segments are saved").
4. Retire manual "click a suggestion" as the primary flow; keep the ranked-alternatives view (now backed by `casting-decision`, not `voice-suggestions`) as the edit surface for the override model — the UI motion is small even though the backend changes substantially.
5. Backward compatibility: any `character_voice_assignments` row with no `casting_decision_id` is treated as `user_locked = true` on the first auto-cast run, so previously hand-cast projects are left exactly as a human set them unless the user explicitly opts into a full re-cast.

## Risks & open questions

- **Local feature-extraction dependency.** Pitch/jitter/spectral extraction needs a local DSP library (e.g. a Praat-binding or `librosa`-equivalent) that is not currently in the stack. Per the local-first/self-contained-dependency constraint, it must be onboarded through Model Center like every other tool, not assumed preinstalled.
- **LLM labeling is coarse and unverified.** A single text-only LLM call per catalog voice, from numeric features with no audio access, will sometimes mislabel ambiguous voices (e.g. androgynous or accented voices near a category boundary). Labels are marked `humanReviewed: false` and treated as preferred-tier (not hard-constraint) evidence until a curator screen — or at minimum spot-checking — confirms them.
- **Catalog size ceiling.** Kokoro's ~50 voices (and Piper's per-language counts) can still be too few for a 300+ character cast even with minor pooling. The fixed-catalog algorithm degrades gracefully via pooling rather than failing, but the real long-term answer for "every character genuinely distinct" is the cloning/parametric path in [tts-engine-strategy.md](../tts/tts-engine-strategy.md).
- **Solver scale at extreme cast sizes.** Some sprawling or fan-fiction-scale texts produce 300+ named entities. A minimum-dialogue-word-count floor for "gets a dedicated voice at all" (below which a character defaults to the narrator, per Step 1's walk-on handling) keeps the cost matrices tractable; this floor should be tuned, not hardcoded blindly.
- **Narrator selection depends on POV detection accuracy.** If [extraction-pipeline-v2.md](../../architecture/extraction-pipeline-v2.md)'s narrative-voice classifier misjudges POV, narrator selection inherits the error. The cheap pronoun-ratio sanity check (§ Step 0) is a partial mitigation, not a full fix.
- **Determinism vs. a growing catalog.** Installing new voices after a project was already auto-cast can change what a *future* unlocked-character rerun would choose, even though the book itself hasn't changed. `catalogVersion` is recorded per decision specifically so this is visible and explainable rather than a silent surprise.
- **Licensing on cloned/series-reused voices.** A cloned voice's `consentRecordId`/`license` must be checked before it is ever offered by auto-cast, and reusing a cloned voice across a series (§7) must re-verify the license still covers the new project's distribution intent — consent is not transitive by assumption.
