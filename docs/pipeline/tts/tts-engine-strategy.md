# TTS Engine Strategy (v2)

Production-grade, local-first text-to-speech for long-form audiobook narration:
model landscape, engine tiering, an emotion/delivery-aware
direction→engine contract, zero-touch character voice synthesis, and the
provider architecture and bake-off protocol needed to select and ship it.

See also:
[`tts-production-upgrade.md`](tts-production-upgrade.md) (current provider
contract — the honest baseline this doc evolves),
[`../casting/automatic-casting-v2.md`](../casting/automatic-casting-v2.md)
(owns the voice-matching *policy*; this doc owns the synthesis *mechanics*),
[`../casting/voice-bible-spec.md`](../casting/voice-bible-spec.md)
(durable voice/consistency rules),
[`../../architecture/local-ai/model-center.md`](../../architecture/local-ai/model-center.md)
(model catalog / download manager),
[`../../platform/cross-platform-strategy.md`](../../platform/cross-platform-strategy.md)
(hardware tiering, mobile constraints, embedded runtime),
[`generative-sound-design.md`](../assembly/generative-sound-design.md)
(ambience/music that shares the audio bus with speech).

> **Truthfulness rule (inherited from the current contract).** This document
> follows the same discipline as
> [`tts-production-upgrade.md`](tts-production-upgrade.md): a control is only
> ever advertised for an engine if the engine can actually receive it. Every
> capability claim below about a specific third-party model is a *hypothesis to
> be confirmed at the local bake-off* (§10), not a verified benchmark. Where the
> author is uncertain about a model's behavior, license, or footprint, the text
> says **verify at bake-off** explicitly. Do not translate any claim here into a
> `direction_support` set until it is measured on our hardware with our text.

---

## 1. Purpose, goals, non-goals

### Purpose
Kokoro-82M is a fine, fast prototype voice, but it is prototype-*grade* for a
production audiobook product: it cannot synthesize new character voices, it
cannot clone a reference, and it conveys **no emotion** — the pipeline already
infers a rich `DirectionProfile` (anger, anguish-as-`somber`/`fearful`,
whisper, urgency, emphasis) and then throws almost all of it away because no
engine can receive more than pace + pauses (see the "critical gap" in the TTS
research report). This document defines the production TTS strategy that closes
that gap while staying **local-first**.

### The quality bar
The target is **long-form audiobook narration**, which is a strictly harder
problem than short-utterance TTS demos. The bar has four axes, all of which
must hold *simultaneously*:

1. **Consistency across hours.** A narrator voice must not drift in timbre,
   loudness, or accent across a 10-hour title. Character voices must be
   identical in chapter 1 and chapter 40, and reproducible after a model
   update or a session restart.
2. **Emotional and delivery range.** The engine must be able to render anger, a
   whisper, mid-sentence laughter, grief/anguish, urgency, warmth — on demand,
   controlled by the `DirectionProfile`, not by luck of prompt.
3. **Distinct character voices.** Every discovered character gets a voice that
   is *recognizably its own* and clearly separated from the narrator, with zero
   manual WAV picking by the user.
4. **Pronunciation control.** Invented names, foreign terms, and homographs
   must be pronounceable via the existing pronunciation dictionary, deterministically.

### Goals
- Replace "pace + pauses only" with a truthful, tiered, emotion-aware synthesis
  path that honors the `DirectionProfile` as far as each engine genuinely allows.
- Generate and persist a **unique, reproducible voice identity per character**
  with no human input required.
- Keep everything runnable **offline** on a mid-range machine; scale up on GPU,
  degrade gracefully to CPU, and never make cloud mandatory.
- Preserve every hard constraint: segment-first, manifest-driven, patchable,
  append-only render history, paths-not-blobs, conservative production.

### Non-goals
- **Not** singing, real-time conversational agents, or sub-100 ms latency. This
  is batch narration; we optimize throughput and consistency over first-token latency.
- **Not** picking a single winning model in this document. Selection is
  evidence-based and happens at the bake-off (§10). This doc narrows the field
  and defines the harness.
- **Not** re-specifying casting/matching policy — that lives in
  [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md). Here we only
  define how a matched profile becomes audio.
- **Not** cloning real people's voices without consent. Novel-voice synthesis is
  the default path; reference cloning stays consent-gated exactly as XTTS-v2 is today.

---

## 2. Requirements matrix

Derived from the product mandate and the existing `DirectionProfile`
(`libs/domain-models/src/echodraft_domain/models.py:500`). Priority: **P0** ship
blocker, **P1** strongly wanted, **P2** future.

| # | Requirement | What it means concretely | Priority | Source of truth |
|---|---|---|---|---|
| R1 | **Emotion / delivery control** | Honor `emotion ∈ {neutral, warm, tense, quiet, urgent, somber, bright, fearful, angry}` + `intensity ∈ [0,1]` at synthesis, not just as metadata | P0 | `DirectionProfile.emotion/intensity/tone` |
| R2 | **Pace control** | `pace ∈ [0.5, 2.0]` transmitted engine-native | P0 (already met by Kokoro/Piper) | `DirectionProfile.pace` |
| R3 | **Whisper** | `whisper=true` produces a genuine breathy low-energy delivery, not just quieter volume | P1 | `DirectionProfile.whisper` |
| R4 | **Emphasis** | `emphasis=true` adds intra-utterance stress on key words | P2 | `DirectionProfile.emphasis` |
| R5 | **Nonverbals** | Mid-line `<laugh>`, `<sigh>`, `<sob>`, breaths where the text/direction implies them | P1 | derived from text + `emotion` |
| R6 | **Style prompt** | Free-text `style_prompt` steers delivery on engines that accept natural-language style | P2 | `DirectionProfile.stylePrompt` |
| R7 | **Pause spacing** | `pauseBeforeMs`/`pauseAfterMs` honored engine-independently at assembly | P0 (already met) | assembly, not engine |
| R8 | **Novel-voice synthesis** | Produce a unique voice per character from a profile (gender/age/accent/timbre) with **no user WAV** | P0 | product mandate; casting v2 |
| R9 | **Voice cloning (opt-in)** | Consent-gated reference-audio conditioning for users who *want* a specific voice | P1 | current XTTS-v2 behavior |
| R10 | **Long-form stability** | No drift, no runaway hallucination, no attention collapse over paragraphs/hours | P0 | quality bar |
| R11 | **Streaming / latency** | Batch RTF < 1.0 on the target tier; streaming decode is a bonus for previews | P1 | perf reality |
| R12 | **Multilingual** | EN first; architecture must not preclude adding languages | P2 | mandate ("any book") |
| R13 | **License** | Weights + inference code usable for local, commercial-ish distribution; caveats surfaced in Model Center | P0 | constraint 4; catalog `license_summary` |
| R14 | **Hardware footprint** | Runs offline within a declared VRAM/RAM budget per tier; CPU fallback exists | P0 | cross-platform strategy |
| R15 | **Determinism / reproducibility** | Same segment + same voice identity + same seed ⇒ same audio; feeds `render_key` freshness | P0 | `rendering.py` cache key |
| R16 | **ASR-verifiable output** | Output can be checked by the existing whisper.cpp hook and re-synthesized on failure | P0 | QA rulebook, `_validate_wav` |

A candidate engine that cannot meet **R8** (novel voice) *or* **R10**
(long-form stability) cannot be a Tier-S default, regardless of demo quality.
Those two are the audiobook-specific gates that eliminate most "great short
demo" models.

---

## 3. Open-weights model landscape (early 2026)

**Read this section as a survey of candidates, not a ranking of verified
results.** The author's knowledge has a cutoff and the open-TTS space moves
monthly; params, licenses, and especially *long-form* behavior must be
re-confirmed at the bake-off. Short-clip demo quality is a notoriously poor
predictor of hour-long-narration quality, so the "quality tier" column is a
*prior*, not a measurement.

### Emotion-control taxonomy (how an engine can even receive feeling)
Every expressive engine exposes control through one (or a mix) of these
mechanisms. This taxonomy is what §5 compiles the `DirectionProfile` *into*:

- **Inline tags** — markup in the text stream, e.g. `<laugh>`, `<sigh>`,
  `[whispering]`. Compositional and precise for nonverbals; requires text
  preprocessing. (Orpheus, Dia-style.)
- **Scalar exaggeration / temperature** — one or two continuous knobs that push
  expressiveness up/down globally for an utterance. Simple, coarse. (Chatterbox-style.)
- **Emotion vector / embedding** — an N-dim conditioning vector (e.g. happy/sad/
  angry/fear axes) mixed into the acoustic model. Fine-grained, interpolatable. (Zonos-style.)
- **Reference audio ("acting ref")** — a short clip whose *prosody and affect*
  are transferred to new text (distinct from cloning *identity*). Most general;
  needs a clip per (voice × emotion). (XTTS/F5/CSM-style.)
- **Natural-language style prompt** — a free-text description of desired
  delivery. Expressive but least deterministic. (Fish/OpenAudio S1-style.)

### Candidate matrix

| Model | ~Params | Emotion mechanism | Cloning | License (verify) | Footprint (verify) | Long-form stability (verify) | Quality prior |
|---|---|---|---|---|---|---|---|
| **Kokoro-82M** (current default) | 82M | none (pace only) | no | Apache-2.0 (weights) | CPU-real-time; ~350 MB ONNX (catalog) | **Strong** — small, deterministic, low hallucination | Good neutral; no range |
| **Piper** | ~10–30M/voice | none | no | MIT | CPU-real-time; tiny | **Strong** — very stable | Fair; robotic |
| **XTTS-v2 / Coqui** | ~0.5–1B | reference audio (prosody) | **yes** (ref WAV) | **Coqui CPML — non-commercial caveat**; project archived/aging | ~4–6 GB VRAM; CPU slow | Moderate — can drift/repeat on long input | Good; aging |
| **Chatterbox** (Resemble AI) | ~0.5B (Llama-backbone) | **scalar exaggeration** + temperature | **yes** (ref WAV) | **MIT** | GPU-favored; mid VRAM | Verify — short-form focus | Very good expressive prior |
| **Orpheus-3B** (Llama-based) | 3B (+smaller variants) | **inline emotive tags** `<laugh>`/`<sigh>`/`<yawn>` | partial (voice presets / zero-shot) | **Apache-2.0** | 3B needs meaningful VRAM (~8–10 GB fp16; less quantized) | Verify — LLM backbone can ramble; needs guardrails | Very good expressive prior |
| **F5-TTS** | ~0.3–0.5B | reference audio (prosody) | **yes** (ref WAV) | **MIT code / CC-mixed data — verify weight terms** | mid VRAM; flow-matching | Verify — generally coherent; watch repetition | Very good |
| **Fish-Speech / OpenAudio S1** | ~0.5–1B | style prompt + reference | **yes** | **verify — mixed/tiered terms** | mid VRAM | Verify | Very good |
| **Dia** (Nari Labs) | ~1.6B | inline nonverbals + **dialogue/turn** control | zero-shot from ref | **Apache-2.0 (verify)** | GPU-favored | Verify — tuned for dialogue, not hour-long solo narration | Good for dialogue |
| **Zonos** (Zyphra) | ~1.6B (transformer + SSM variants) | **emotion vector** (happy/sad/anger/fear/…) + reference | **yes** | **Apache-2.0 (verify)** | GPU-favored, mid VRAM | Verify | Very good; explicit emotion axis |
| **Sesame CSM-1B** | 1B | reference/context (conversational) | ref-conditioned | **Apache-2.0 (verify)** | mid VRAM | Verify — conversational framing, not narration | Good |
| **Higgs Audio v2** | large (verify) | verify (multi-speaker/expressive) | verify | **verify** | large (verify) | Verify | Unknown — treat as speculative |

Reading of the field for *this* product:

- The **explicit-control** models (Orpheus tags, Chatterbox exaggeration, Zonos
  emotion vector) are the most attractive because their control surface maps
  cleanly and *deterministically* onto our `DirectionProfile` — we can compile
  emotion → a concrete parameter and know what we asked for.
- **Reference-only** models (XTTS/F5/Fish/CSM) can still deliver emotion, but
  via the "acting ref" mechanism (§5.4), which is more moving parts (a clip bank
  per character × emotion) and less crisp.
- **XTTS-v2's CPML license is a genuine blocker** for a commercial-ish
  distributable product and is why it stays opt-in/experimental, not a default —
  independent of its quality.
- **Orpheus-3B's size** is the main footprint risk; a quantized build may bring
  it into the Tier-S budget — **verify at bake-off**.

---

## 4. Recommended engine tiering

The strategy is **tiered by hardware and honesty**, mirroring the existing
`direction_support` discipline: each tier advertises only what it can truly do.
The pipeline picks the highest tier the detected hardware and installed models
support, and a project may pin a tier for reproducibility.

```
                     control richness  ─────────────────────────────►
  Tier S  "Expressive"   full emotion + novel voices + cloning     GPU
  Tier A  "Standard"     pace + pauses + limited style             CPU-capable
  Tier C  "Cloud"        provider-defined (OFF by default)         opt-in only
```

### Tier S — Expressive (GPU default)
- **Purpose:** the real product voice. Emotion, whisper, nonverbals, distinct
  synthesized character voices.
- **Primary candidates (pick 1–2 at bake-off):**
  1. **Chatterbox** — MIT, cloning + a simple exaggeration knob that maps well
     to `intensity`. Strong prior for expressive delivery; small enough control
     surface to be reliable. Lead candidate on *licensing + control simplicity*.
  2. **Orpheus-3B** — Apache-2.0, inline emotive tags that map directly to
     nonverbals (R5) and emotion (R1). Lead candidate on *expressive range*, with
     footprint (R14) and LLM-rambling (R10) as the risks to prove out.
  - **Zonos** is the strong third, kept as a backup specifically because its
    explicit emotion *vector* is the cleanest possible target for
    `emotion+intensity`; promote it if Chatterbox/Orpheus fail the stability gate.
- **Truthful `direction_support` (target, pending bake-off):**
  `{pace, intensity, tone, emotion, emphasis, whisper, stylePrompt (Orpheus/style-capable only), pauseBeforeMs, pauseAfterMs}`.
  Each element is only added after §10 confirms the engine honors it.

### Tier A — Standard (CPU-capable default)
- **Purpose:** runs on any machine with no GPU; the fast/low-end path and the
  guaranteed fallback. **Kokoro-82M stays here as the default**, with **Piper**
  as an even-lighter alternative.
- **Truthful `direction_support` (unchanged from today):**
  Kokoro managed ONNX → `{pace, pauseBeforeMs, pauseAfterMs}`;
  Piper → `{pace, pauseAfterMs, pauseBeforeMs}`.
  Emotion/whisper/emphasis are **not** claimed here — they degrade per the
  fallback ladder (§5.5). This is the same honest position as
  [`tts-production-upgrade.md`](tts-production-upgrade.md) and must not regress.
- **Why keep it:** deterministic, tiny, extremely stable over long text (R10),
  and the only tier guaranteed to satisfy R14 on a phone/old laptop.

### Tier C — Cloud (optional, OFF by default)
- **Purpose:** an *optional* escape hatch for users who explicitly want a hosted
  premium voice. **Never installed or enabled by default; never a silent
  fallback** (constraint 4). Gated behind the same explicit-consent pattern as
  reference voices today, plus a network-egress consent.
- The pipeline treats a cloud provider as just another `TtsProvider`
  implementation whose `readiness()` fails closed unless the user has opted in.
- Its `direction_support` is whatever the vendor API genuinely exposes, declared truthfully.

**Selection rule at render time:** resolve the project's pinned tier → else the
highest tier whose model is installed and whose hardware check passes → else
Tier A. The chosen provider identity is recorded in `render_identity()` and thus
in the `render_key`, so switching tiers correctly stales only affected renders.

---

## 5. Direction → engine contract v2

Today `DirectionProfile` compiles to *pace + pauses* and nothing else. v2
defines a **compiler** from the `DirectionProfile` to each engine's native
control surface, plus a **fallback ladder** so that a missing control degrades
predictably instead of lying.

The compiler is a pure function
`compile_direction(profile, engine_capabilities) -> EngineControls` living in the
engine host (§7). It never invents a control the engine lacks; anything it cannot
express is returned in `unsupportedDirection` (the existing field) and handled by
the ladder (§5.5). This keeps `effectiveDirection` honest, exactly as the current
adapters already do.

### 5.1 Emotion + intensity → control (per mechanism)

The core mapping table. `emotion` picks *what*, `intensity` picks *how much*.

| `emotion` | Tag-based target (Orpheus/Dia) | Exaggeration/temp (Chatterbox) | Emotion vector (Zonos) | Acting-ref bucket (XTTS/F5) |
|---|---|---|---|---|
| neutral | (none) | exagg=baseline | vec≈0 | `neutral` ref |
| warm | `[warm]`/soft prosody | exagg slightly ↑, temp ↓ | +warmth/+happy small | `warm` ref |
| bright | (none)/upbeat | exagg ↑ | +happy | `bright` ref |
| tense | (none) | exagg ↑, temp ↓ | +fear/+anger small | `tense` ref |
| urgent | (none) + pace↑ | exagg ↑, temp ↓ | +anger/arousal, pace↑ | `urgent` ref |
| somber (anguish) | `<sigh>` seed + slow | exagg mid, temp ↓ | +sad | `somber` ref |
| fearful | (none) | exagg ↑ | +fear | `fearful` ref |
| angry | (none) | exagg high | +anger | `angry` ref |
| (whisper flag) | `[whispering]` | dedicated whisper ref if present | +breathiness / low energy | `whisper` ref |

`intensity` scales the magnitude: for scalar engines it maps roughly to
`exaggeration = clamp(base + k·intensity)`; for vector engines it scales the
chosen axis's magnitude; for tag engines high intensity may *duplicate/strengthen*
the nonverbal (e.g. `<laugh>` → a longer laugh token) — **verify per engine**.
Exact constants are calibrated in the bake-off, not guessed here.

> Caution: pushing expressiveness knobs hard degrades intelligibility and
> stability on every one of these models. The voice bible's `maxExpressiveness`
> and `narrationRestraint` (see [`voice-bible-spec.md`](../casting/voice-bible-spec.md))
> **cap** the compiled magnitude. Narrator lines default to restraint; dialogue
> gets more range. This is the "conservative, tasteful" constraint made mechanical.

### 5.2 Tag injection (tag-based models) — algorithm

For engines whose control is inline markup, the compiler runs a text
preprocessing pass that turns direction + textual cues into tags:

```
compile_tags(text, profile):
  out = text
  # 1. Emotion/whisper → wrapping style tag (engine-specific vocabulary)
  if profile.whisper:          out = wrap(out, WHISPER_TAG[engine])
  elif profile.emotion != neutral and engine.supports_emotion_tag(profile.emotion):
                               out = wrap(out, EMOTION_TAG[engine][profile.emotion])
  # 2. Nonverbals from the text itself (only if direction permits, capped by bible)
  #    Detect authored cues; DO NOT hallucinate laughter the text didn't imply.
  out = replace_authored_cues(out)   # "he laughed" adjacency, "*sigh*", "ha ha" → <laugh>/<sigh>
  # 3. Emphasis → per-word stress markup on capitalized/italic/bible-flagged words
  if profile.emphasis:         out = mark_emphasis(out)
  # 4. Pauses handled at assembly, NOT as tags (keep pause math in one place)
  return out
```

Rules: (a) **nonverbal insertion is evidence-gated** — a `<laugh>` is only
injected where the manuscript actually signals it (dialogue tag "laughed", an
onomatopoeia, an authored `*sigh*`), never invented from `emotion` alone, to
protect against comedic tone-breaking (a do-not-cross rule in the voice bible).
(b) Pronunciation replacement (existing feature) runs **before** tag injection so
tags never land inside a replaced token. (c) Tags the target engine does not
recognize are stripped, not passed through as literal text.

### 5.3 Scalar / temperature params (Chatterbox-style)
The compiler emits a small struct `{exaggeration, temperature, cfg_weight?}` from
`emotion+intensity` per §5.1, clamped by the bible. These pass straight to the
engine call. Whisper, if the engine has no whisper mode, falls back to a whisper
*acting ref* (§5.4) or to the ladder (§5.5) — it is **not** faked by lowering volume.

### 5.4 Emotion embeddings / vectors and acting refs (reference conditioning)
Two related reference mechanisms:

- **Emotion vector** (Zonos): compile `emotion+intensity` → an N-dim vector by
  the §5.1 axis mapping, scaled by intensity, capped by the bible. Deterministic
  and interpolatable.
- **Acting refs** (reference-conditioned engines with no explicit emotion knob,
  e.g. XTTS/F5): maintain a per-character **clip bank** — for each character
  voice, a short clip *in that character's own synthesized voice* for each needed
  emotion bucket (`neutral, warm, tense, urgent, somber, fearful, angry, whisper`).
  These are generated **once** when the character voice is created (§6),
  validated by ASR, and cached on the filesystem (paths in the voice profile,
  never blobs in the DB — constraint 7). At render time the compiler selects the
  bucket for the segment's `emotion` and conditions synthesis on that clip. This
  gives emotion to a clone-only engine without a human ever recording anything.

Acting refs are the most expensive mechanism (storage + one-time generation) and
are only used for Tier-S engines that lack a direct emotion parameter.

### 5.5 Fallback ladder (graceful degradation)
When an engine cannot honor a requested control, degrade in this fixed order and
record the degradation in render metadata + `unsupportedDirection` (never silently):

```
For each requested control C on a segment:
  1. Engine-native path exists?           → use it.
  2. Else an equivalent mechanism exists?  → translate (tag↔vector↔exaggeration↔acting-ref).
  3. Else assembly-level substitute?       → e.g. emphasis/pause approximated with
                                             pauseBefore/After spacing at assembly.
  4. Else                                  → render prosody-NEUTRAL for that control,
                                             mark it unsupported, keep pauses.
```

Concrete: on Tier-A Kokoro, an `angry` segment renders as neutral pace-adjusted
speech with assembly pauses, and metadata says `emotion` was unsupported. The
audiobook is never *wrong* — it is just less expressive on weak hardware, and the
UI can truthfully show which segments would gain from a GPU tier. This is the
same fail-honest philosophy as the current empty-`effectiveDirection` adapters.

---

## 6. Character voice synthesis pipeline (zero manual input)

Goal (R8): every discovered character gets a **unique, consistent, reproducible**
voice with no user picking WAVs. The matching *policy* (which archetype a
character should sound like, narrator selection preferences) is owned by
[`automatic-casting-v2.md`](../casting/automatic-casting-v2.md); this section owns
the **synthesis mechanics** that turn a resolved character profile into a durable
voice identity.

### 6.1 What a "voice identity" is
A synthesized voice is pinned by a **voice identity record** persisted in the
voice profile (extending `VoiceProfileRecord`, which today has no real metadata
columns). It stores whichever of these the chosen engine uses, so renders are
reproducible across sessions *and* model updates:

```json
{
  "voiceIdentityId": "vid_7f3a…",
  "engine": "chatterbox",              // engine family this identity is valid for
  "engineModelVersion": "…",           // pin; a model change re-validates, not silently drifts
  "method": "seed | embedding | reference_clip",
  "seed": 480213,                      // for seed-conditioned generation
  "voiceEmbedding": "voices/vid_7f3a/embedding.npy",  // path, not blob
  "referenceWavPath": "voices/vid_7f3a/identity.wav", // canonical identity clip (synth or consented clone)
  "actingRefs": { "angry": "…/angry.wav", "whisper": "…/whisper.wav", "…": "…" },
  "profileConstraints": { "gender": "female", "ageBand": "adult", "accent": "en-GB", "timbre": "warm-low" }
}
```

### 6.2 Generating a novel voice from a character profile — algorithm
Inputs from cast discovery: `gender`, `age band`, `accent`, coarse `timbre`
descriptors. Two supported generation methods depending on the engine:

**A. Embedding-space sampling (engines with a speaker-embedding space):**
```
generate_voice(profile, existing_identities):
  region  = embedding_region(profile.gender, profile.ageBand, profile.accent, profile.timbre)
  for attempt in 1..N:
     cand = sample(region, seed = hash(projectId, characterId, attempt))
     if min_distance(cand, existing_identities.embeddings) >= D_MIN:   # collision avoidance
        return persist_identity(cand, seed)
  return persist_identity(farthest_candidate, seed)   # best-effort if crowded
```

**B. Seed-conditioned generation (engines whose voice is a function of a seed +
descriptors):** identical loop, but the identity is `(seed, descriptors)` and the
"distance" is measured on a speaker embedding *extracted from a short probe render*
of each candidate (using our ASR/speaker-embedding hook), since the engine has no
native embedding to compare.

**Collision avoidance (R8's "recognizably its own"):** maintain the set of
project voice embeddings; require `distance ≥ D_MIN` (a cosine/L2 threshold
calibrated at bake-off). This guarantees two characters in the same book never
collapse to the same voice, and enforces the voice-bible rule that major
characters get distinct voices and contrast clearly with the narrator. `D_MIN` is
relaxed only when the character count exceeds the space's practical capacity
(then minor characters may intentionally share, per the bible).

**Determinism (R15):** all sampling is seeded from
`hash(projectId, characterId, attempt)`, so voice generation is reproducible.
The resulting identity is *persisted*, so even a nondeterministic engine yields
the same voice forever by re-conditioning on the stored embedding/reference clip
rather than re-sampling.

### 6.3 Narrator selection heuristic
The narrator is the most-heard voice, so it is chosen for **stability and
restraint, not range**: prefer a low-`maxExpressiveness`, high-clarity identity
distinct (by ≥ `D_MIN`, ideally larger margin) from all major characters. Default
to a neutral accent unless the manuscript/first-person voice implies otherwise.
The narrator identity is locked in the voice bible and, per that spec, must not
drift between chapters without an explicit project-level change (which stales all
chapters). Policy details: [`automatic-casting-v2.md`](../casting/automatic-casting-v2.md).

### 6.4 Persistence, patchability, and model updates
- The identity record lives with the voice profile; **paths only**, artifacts on
  disk (constraint 7).
- Because the identity (embedding/seed/reference clip) is pinned, a re-render
  months later reproduces the same voice — the core long-form consistency
  guarantee.
- On an engine/model version change, the stored identity is **re-validated**
  (re-embed the identity clip, confirm distance) rather than silently reused; a
  material mismatch surfaces as a voice-bible "stale voice" issue and triggers QA
  rerun, exactly as the bible requires for voice changes.
- Consented cloning (R9) uses the *same* record with `method: reference_clip` and
  a user-supplied WAV, keeping the current XTTS consent gate.

---

## 7. Provider architecture v2

The current `TtsProvider` ABC is subprocess-per-call for most engines and runs a
single resident Kokoro worker with a global lock (one synthesis at a time). That
is fine for an 82M ONNX model but is fatal for 0.5–3B GPU models, where
per-call model load would dominate wall-clock. v2 introduces an **engine host**.

### 7.1 Engine host (persistent in-process model)
- A long-lived **engine host process** loads the selected Tier-S model **once**
  into memory (GPU or CPU) and serves synthesis requests over the same
  newline-JSON worker protocol the managed Kokoro worker already uses
  (`tts_worker.py`). This generalizes `ManagedKokoroWorker` to
  `EngineHost(engine_id, device)`.
- Rationale: amortize multi-GB model load across thousands of segments; keep the
  model warm across a chapter; avoid Python import cost per segment (XTTS today
  pays a full `TTS.api` import per call).
- The `TtsProvider` ABC gains an optional `open_host()/synthesize(request)/close()`
  path; adapters that have no persistent state (mock) keep the simple `preview()`.

### 7.2 Request batching
- The host accepts a **batch** of same-voice, same-engine-control segments and
  decodes them together where the engine supports batched inference, improving
  GPU utilization. Batching is bounded by VRAM and never crosses voice/direction
  boundaries in a way that would blur identity.
- Batching is an *optimization only*: each segment still produces its own
  artifact and its own append-only `SegmentRenderRecord`; the `render_key` is
  per-segment and unaffected. Segment-first is preserved.

### 7.3 GPU detection / placement
- A `device_plan()` probe selects, in order: **CUDA** (NVIDIA) → **Metal/MPS**
  (Apple Silicon) → **DirectML** (Windows non-NVIDIA) → **CPU**. The probe
  result gates which tier is even offered (§4) and is surfaced in Model Center so
  the user understands why a tier is/ isn't available.
- Device choice is recorded in render metadata for traceability but is **excluded
  from the `render_key`** (like `workerMode` today) — CPU vs GPU of the *same
  model + seed* must not stale audio, matching the existing freshness rule.
- **Note the current XTTS adapter hardcodes `gpu=False`** — v2 replaces that with
  `device_plan()`.

### 7.4 Chunking long segments with prosody continuity
Some segments (or the model's max input length) require splitting. To avoid audible
seams:
- Split on **sentence/clause boundaries** (never mid-word); keep chunks under the
  engine's stable-length limit (measured, not assumed — §8).
- Maintain **prosody continuity** by conditioning each chunk on the tail context
  of the previous chunk where the engine supports context carry (LLM-backbone and
  reference models often do), and by **overlap-decode + equal-power crossfade**
  (a short overlap region, cross-faded ~20–40 ms) at the join otherwise. This
  reuses the crossfade machinery assembly already has for ambience loops.
- All chunk joins happen *inside* one segment's render so the segment stays the
  atomic unit; assembly still sees one clip per segment.

### 7.5 Output validation and retry-on-hallucination
Long-form generative TTS *will* occasionally hallucinate (extra/missing words,
loops, truncation). v2 formalizes a validation gate reusing the existing
whisper.cpp ASR hook and `analyze_wav`:

```
validate(render, text):
  asr = whisper_cpp(render.wav)
  wer = word_error_rate(asr.text, expected_synthesis_text)
  dur_ratio = render.duration / expected_duration(text, pace)
  flags = []
  if wer > WER_MAX:                    flags += "asr_word_mismatch"   # existing QA category
  if dur_ratio > DUR_HI or < DUR_LO:   flags += "truncation|runaway"
  if silence_ratio(render) > SIL_MAX:  flags += "excessive_silence"
  return flags
```

Retry policy: on a hallucination flag, **re-synthesize with a different seed**
(and, if it recurs, drop expressiveness one rung down the §5.5 ladder), up to
`MAX_RETRIES`. Each attempt is an appended `SegmentRenderRecord` (append-only
history, constraint 6) — nothing is overwritten. Persistent failure raises a
durable render QA `issue` (existing categories: `asr_word_mismatch`,
`truncation`, `excessive_silence`) for the review queue rather than shipping bad
audio. Deterministic engines (Kokoro/Piper) rarely trip this; it mainly guards Tier S.

---

## 8. Long-form quality engineering

Consistency over hours is an engineering discipline, not a model property:

- **Sentence-level chunking rules.** Prefer one synthesis call per sentence for
  expressive engines (bounds drift and makes retries cheap); group short adjacent
  sentences up to a measured stable-length ceiling per engine. Never split
  mid-clause. Ceilings are established empirically (§10), not assumed.
- **Seed pinning per segment.** Each segment renders with a stable seed derived
  from `hash(voiceIdentity.seed, segmentId, revision)`. This makes renders
  reproducible (R15) and makes a retry's "different seed" well-defined
  (`+attempt`). The seed participates conceptually in the render fingerprint via
  direction/voice identity, so re-renders are stable.
- **Loudness consistency pre-master.** Before the existing chapter loudnorm pass,
  normalize each *segment* to a consistent internal target (e.g. per-segment gain
  toward a common RMS/LUFS anchor) so no single line is jarringly loud/soft. The
  final two-pass loudnorm to −19 LUFS / −3 dBTP (existing `mastering.py`) stays
  the authority for the delivered chapter; segment pre-leveling just removes
  intra-chapter variance that mastering alone cannot fix.
- **Pronunciation dictionary integration.** Unchanged contract: replacement runs
  **before** render-key generation and before tag injection (§5.2), invalidating
  only impacted segments (per voice-bible rules). Phonetic entries should be
  passed to engines that accept phoneme input (Piper/Kokoro phonemizers) and
  otherwise applied as `replacementText`.
- **Regression listening tests.** Maintain a fixed **golden set** of segments
  (the §10 test scripts) rendered on every engine/version bump; diff RTF, LUFS,
  ASR-WER, and keep short human spot-checks. A tier is not promoted if the golden
  set regresses.

---

## 9. Hardware tiers & model management

### Budgets (targets; confirm real numbers at bake-off)

| Tier | Device | VRAM/RAM budget | Model examples | Approx download |
|---|---|---|---|---|
| S | Discrete GPU (≥8 GB VRAM) or Apple Silicon (≥16 GB unified) | 4–10 GB working set | Chatterbox / Orpheus-3B (quantized) / Zonos | ~1–6 GB per model (verify) |
| A | Any CPU, ≥4 GB free RAM | <1 GB | Kokoro-82M ONNX (~350 MB, in catalog), Piper (tens of MB) | 0.05–0.4 GB |
| C | Network + explicit consent | n/a (hosted) | cloud provider | n/a |

Mobile (iOS/Android) generally lands on **Tier A** (Kokoro/Piper) given thermal
and memory limits; a phone with a capable NPU *may* run a small quantized
expressive model — treat as future work and defer to
[`cross-platform-strategy.md`](../../platform/cross-platform-strategy.md), which
owns the per-platform runtime and download-manager decisions.

### Model Center catalog integration
New declarative entries in `model_catalog.yaml`
(`apps/api/src/echodraft_api/local_ai/model_catalog.yaml`) alongside the existing
`kokoro_82m_onnx`, each with `capability: tts`, honest `license_summary`,
`size_mb`, and per-platform packages/download URLs, e.g.:

```yaml
  chatterbox_tts:
    display_name: Chatterbox (Resemble AI)
    capability: tts
    provider: chatterbox
    install_type: managed_weights      # downloaded + verified by Model Center
    required: false                     # Tier-S optional; Kokoro stays the required baseline
    size_mb: 0000                        # fill from real artifact at bake-off
    license_summary: MIT (verify weights + inference deps before distribution)
    description: Expressive Tier-S local TTS with cloning and exaggeration control.
```

- **Kokoro stays `required: true`**; every expressive engine is `required: false`
  and opt-in, so a clean install always has a working local voice with no large
  download.
- Downloads, checksums, consent flags, and status tracking reuse the existing
  `ModelInstallationRecord`/`ModelInstallJobRecord` machinery. License caveats
  (especially XTTS CPML, and any "verify" weight terms) must surface at the
  consent step, not be buried.

---

## 10. Bake-off protocol (evidence-based selection)

No engine graduates to a default tier without passing this on our hardware. The
whole point is to replace the priors in §3 with measurements.

### Test scripts (the fixed evaluation corpus)
1. **Neutral narration** — a ~500-word third-person passage. Tests baseline
   quality and drift.
2. **Angry outburst** — dialogue lines flagged `emotion=angry`, rising `intensity`.
3. **Whisper** — `whisper=true` lines interleaved with normal narration (tests
   real breathy delivery vs faked volume).
4. **Laughter mid-sentence** — authored `<laugh>`/"he laughed" cues (tests
   nonverbal injection §5.2 and comedic-tone control).
5. **Grief/anguish** — `emotion=somber`, slow, `<sigh>` (tests the "anguish" case
   the mandate calls out explicitly).
6. **Long-paragraph stability** — a single 1,500+ word block (tests R10:
   truncation, looping, attention collapse, loudness drift).
7. **Multi-character dialogue** — 3+ distinct voices in one scene (tests identity
   distinctness and contrast with narrator).
8. **Pronunciation** — invented names + homographs via the dictionary.

### Scoring rubric (per engine × script)
| Dimension | How measured |
|---|---|
| Intelligibility / accuracy | ASR-WER via whisper.cpp (automatic) |
| Long-form stability | truncation/loop/silence flags over script 6 (automatic + listen) |
| Emotion fidelity | blind human 1–5: does it *sound* angry/whispered/grieving? |
| Voice distinctness | speaker-embedding pairwise distance on script 7 |
| Consistency | timbre/loudness variance across a rendered chapter |
| Naturalness | blind human 1–5 MOS-style |
| License fit | pass/fail against commercial-ish local distribution (R13) |

### Latency / RTF measurement
- **RTF** = synthesis wall-time ÷ audio duration, measured **warm** (model
  already loaded in the engine host) and reported per device (CUDA/MPS/DirectML/
  CPU). Tier-S target: warm RTF < 1.0 on the reference GPU; Tier-A target: RTF
  comfortably < 1.0 on a mid CPU.
- Also record **cold model-load time** (justifies the engine host, §7.1) and
  **peak VRAM/RAM** (validates the §9 budgets).

### Decision
Pick **1–2 Tier-S engines** that pass the R10 stability gate *and* R13 license
gate, then rank by emotion fidelity + naturalness. Record results as a durable
manifest/plan under `plans/` so the choice is auditable and re-runnable on the
next model bump.

---

## 11. Migration path, risks, open questions

### Migration (evolve, don't rewrite)
1. **Keep the ABC, add the host.** Generalize `tts_worker.py`'s resident worker
   into a device-aware `EngineHost`; existing Kokoro/Piper/XTTS/Mock adapters keep
   working unchanged as Tier-A/experimental providers. No behavior regresses.
2. **Land the direction compiler** (`compile_direction`, §5) with **only Kokoro/
   Piper mappings first** (i.e. today's honest pace+pauses) so the plumbing ships
   before any new model — the `direction_support`/`unsupportedDirection`/
   `effectiveDirection` contract is preserved bit-for-bit.
3. **Bake-off (§10)** selects the Tier-S engine(s); add its Model Center catalog
   entry and adapter; wire its real `direction_support` only for controls that passed.
4. **Voice identity records** (§6) extend `VoiceProfileRecord` with metadata
   columns + on-disk artifact paths; casting v2 begins writing them.
5. **render_key compatibility.** The fingerprint already includes provider +
   model identity + resolved direction + voice; adding a new provider naturally
   produces new keys for new renders while **all existing Kokoro renders keep
   their keys and stay valid**. No history is rewritten; new engines only ever
   *append* new `SegmentRenderRecord`/`ChapterRenderRecord` rows (constraint 6).
   Device and worker mode remain excluded from the key.

### Risks
- **Footprint vs quality tension.** The most expressive models (Orpheus-3B) may
  not fit the Tier-S budget without quantization that hurts quality. Mitigation:
  Chatterbox/Zonos as smaller fallbacks; quantized builds evaluated at bake-off.
- **Hallucination on long text.** LLM-backbone TTS can ramble. Mitigation: §7.5
  ASR-gated retry + sentence chunking + the deterministic Tier-A fallback.
- **License traps.** XTTS CPML is non-commercial; some "MIT code / restricted
  weights" splits are subtle. Mitigation: R13 is a hard bake-off gate; caveats
  surfaced in Model Center consent.
- **Voice reproducibility across model versions.** A model update can shift a
  seed's voice. Mitigation: persist embeddings/reference clips and re-validate
  (§6.4) rather than re-sample.
- **Expressiveness harming clarity/consistency.** Mitigation: bible-capped
  magnitudes (§5.1), narrator restraint, regression listening (§8).

### Open questions (resolve at/after bake-off)
- Which 1–2 Tier-S engines actually pass R10 + R13 on our hardware?
- Does any candidate support true batched inference (§7.2), or is per-segment the
  practical unit?
- Do we need per-character *acting-ref banks* (§5.4), or do the shortlisted
  engines expose direct emotion control that makes them unnecessary?
- What are the real `D_MIN` collision threshold and `WER_MAX`/duration retry
  thresholds? (Calibrate empirically.)
- Multilingual (R12): which shortlisted engine has the best non-EN path, and does
  that change the Tier-S pick for non-English titles?
- Can any quantized expressive model realistically run on high-end mobile NPUs, or
  is Tier A the permanent mobile answer?
