from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import mastering

SAMPLE_RATE = 16_000
SCHEMA_VERSION = "tier0-sound-1.0.0"
LICENSE_NOTE = (
    "CC0-1.0: project-authored procedural synthesis recipe dedicated to the public domain."
)

# Below this Jaccard overlap, an SFX request is treated as unsupported by the bank rather
# than substituted with the nearest (but wrong) entry: silence is a safe fallback for an
# explicit textual event like "gunshot" the bank has no asset for, a mismatched sound
# effect is not. Ambience/music lookups keep the existing "best available match" fallback
# (a miss there degrades to a generic bed, per the design doc), since a slightly-off
# ambience texture is far less jarring than a wrong one-shot SFX.
MIN_SFX_MATCH_JACCARD = 0.2

# Recipes that are stationary/periodic-enough to loop: seam-forcing (matching the last
# sample to the first) is safe and desirable for these. One-shot SFX recipes must never be
# seam-forced -- snapping a percussive tail back to the (near-zero) head sample injects an
# audible click, so they get a short fade-out tail instead (see `_finalize`).
LOOPABLE_RECIPES = frozenset(
    {
        "room",
        "wind",
        "rain",
        "fire",
        "ocean",
        "forest",
        "urban",
        "crowd",
        "pad_somber",
        "pad_bright",
        "pad_tense",
    }
)
ONE_SHOT_FADE_MS = 20.0


@dataclass(frozen=True)
class BankEntry:
    id: str
    name: str
    asset_type: str
    tags: frozenset[str]
    recipe: str


@dataclass(frozen=True)
class ResolvedTierZeroAsset:
    entry: BankEntry
    path: Path
    duration_ms: int
    cache_key: str


BANK = (
    BankEntry("room_tone", "Quiet room tone", "ambience", frozenset({"interior", "quiet", "room"}), "room"),
    BankEntry("wind", "Distant wind", "ambience", frozenset({"wind", "exterior", "wilderness"}), "wind"),
    BankEntry("rain", "Steady rain", "ambience", frozenset({"rain", "storm", "exterior"}), "rain"),
    BankEntry("fire", "Low fire", "ambience", frozenset({"fire", "hearth", "camp", "interior"}), "fire"),
    BankEntry("ocean", "Distant ocean", "ambience", frozenset({"ocean", "ship", "coast", "exterior"}), "ocean"),
    BankEntry("forest", "Quiet forest", "ambience", frozenset({"forest", "wilderness", "exterior"}), "forest"),
    BankEntry("urban_night", "Urban night", "ambience", frozenset({"city", "street", "urban", "night"}), "urban"),
    BankEntry("crowd", "Distant crowd", "ambience", frozenset({"crowd", "market", "tavern", "public"}), "crowd"),
    BankEntry("thunder", "Thunder", "sfx", frozenset({"thunder", "storm"}), "thunder"),
    BankEntry("door_slam", "Door slam", "sfx", frozenset({"door", "door_slam", "interior"}), "door"),
    BankEntry("knock", "Knock", "sfx", frozenset({"knock", "door", "interior"}), "knock"),
    BankEntry("footsteps", "Sparse footsteps", "sfx", frozenset({"footsteps", "walking", "running"}), "footsteps"),
    BankEntry("glass_break", "Glass break", "sfx", frozenset({"glass", "glass_break"}), "glass"),
    BankEntry(
        "music_pad_somber",
        "Somber pad",
        "music",
        frozenset({"somber", "music", "pad", "minor"}),
        "pad_somber",
    ),
    BankEntry(
        "music_pad_bright",
        "Bright pad",
        "music",
        frozenset({"bright", "music", "pad", "major"}),
        "pad_bright",
    ),
    BankEntry(
        "music_pad_tense",
        "Tense pad",
        "music",
        frozenset({"tense", "music", "pad", "cluster"}),
        "pad_tense",
    ),
)

# root/third/fifth/octave partials (Hz) per pad mood. Somber sits in a low minor register,
# bright sits an octave up in a major register, and tense is a sustained low minor-second
# cluster (root + b2 + 5th) kept deliberately dissonant and quiet.
_PAD_CHORDS: dict[str, tuple[float, ...]] = {
    "pad_somber": (110.00, 130.81, 164.81, 220.00),
    "pad_bright": (220.00, 277.18, 329.63, 440.00),
    "pad_tense": (110.00, 116.54, 164.81),
}
_PAD_GAIN: dict[str, float] = {
    "pad_somber": 0.05,
    "pad_bright": 0.05,
    "pad_tense": 0.03,
}


class TierZeroSoundBank:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root

    def resolve(
        self,
        tags: list[str],
        *,
        asset_type: str,
        duration_ms: int,
        retry: int = 0,
    ) -> ResolvedTierZeroAsset:
        normalized = {tag.strip().casefold().replace("-", "_") for tag in tags if tag.strip()}
        candidates = [entry for entry in BANK if entry.asset_type == asset_type]
        if not candidates:
            raise ValueError(f"Unsupported Tier-0 asset type: {asset_type}.")
        ranked = sorted(
            candidates,
            key=lambda item: (-_jaccard(normalized, set(item.tags)), item.id),
        )
        entry = ranked[0]
        if asset_type == "sfx" and _jaccard(normalized, set(entry.tags)) < MIN_SFX_MATCH_JACCARD:
            # No bank entry is actually a plausible match for this event (e.g. "gunshot",
            # which the bundled bank does not cover): degrade to no cue rather than
            # substitute a confidently-wrong sound effect.
            raise ValueError(
                f"No Tier-0 SFX bank entry matches tags {sorted(normalized)!r}."
            )
        bounded_duration = max(250, min(60_000, duration_ms))
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "entryId": entry.id,
            "durationMs": bounded_duration,
            "retry": retry,
        }
        cache_key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        root = self.cache_root / cache_key[:2] / cache_key
        path = root / "asset.wav"
        if not path.is_file():
            root.mkdir(parents=True, exist_ok=True)
            samples, rate = _synthesize(entry.recipe, bounded_duration, seed=int(cache_key[:16], 16))
            _write_wav(path, samples, rate)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        **payload,
                        "cacheKey": cache_key,
                        "name": entry.name,
                        "assetType": entry.asset_type,
                        "tags": sorted(entry.tags),
                        "license": LICENSE_NOTE,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return ResolvedTierZeroAsset(entry, path, bounded_duration, cache_key)


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


def _synthesize(recipe: str, duration_ms: int, *, seed: int) -> tuple[np.ndarray, int]:
    if recipe == "room":
        # Reuse the mastering module's own room-tone generator (44.1 kHz, ~-70 dBFS pink-
        # ish noise) instead of reimplementing a fixed-rate room bed here.
        samples = mastering.room_tone(duration_ms, mastering.SAMPLE_RATE)
        return samples, mastering.SAMPLE_RATE
    count = max(1, int(SAMPLE_RATE * duration_ms / 1000))
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(count)
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    if recipe == "wind":
        gust = 0.45 + 0.35 * np.sin(2 * np.pi * 0.11 * time + 0.7)
        signal = 0.035 * _moving_average(noise, 120) * gust
    elif recipe == "rain":
        drops = (rng.random(count) < 0.0025) * rng.uniform(0.2, 0.7, count)
        signal = 0.025 * noise + 0.08 * _moving_average(drops, 4)
    elif recipe == "fire":
        crackle = (rng.random(count) < 0.0012) * rng.uniform(-1, 1, count)
        signal = 0.018 * _moving_average(noise, 35) + 0.12 * crackle
    elif recipe == "ocean":
        swell = 0.35 + 0.3 * (1 + np.sin(2 * np.pi * 0.08 * time)) / 2
        signal = 0.04 * _moving_average(noise, 80) * swell
    elif recipe == "forest":
        chirps = (rng.random(count) < 0.00018) * np.sin(2 * np.pi * 1800 * time)
        signal = 0.012 * _moving_average(noise, 70) + 0.045 * chirps
    elif recipe in {"urban", "crowd"}:
        murmur = _moving_average(noise, 24 if recipe == "crowd" else 45)
        hum = np.sin(2 * np.pi * (80 if recipe == "crowd" else 55) * time)
        signal = 0.018 * murmur + 0.006 * hum
    elif recipe in _PAD_CHORDS:
        signal = _music_pad(recipe, time)
    else:
        signal = _one_shot(recipe, count, time, rng, noise)
    signal = np.clip(signal, -0.35, 0.35)
    signal = _finalize(signal, recipe)
    return np.asarray(signal * 32767, dtype="<i2"), SAMPLE_RATE


def _music_pad(recipe: str, time: np.ndarray) -> np.ndarray:
    """A sustained, soft chord pad: root/third(ish)/fifth/octave partials under a slow
    attack/release envelope plus a gentle amplitude LFO (tremolo) for organic movement.
    Mood-parameterized per ``_PAD_CHORDS``/``_PAD_GAIN``: somber sits in a low minor
    register, bright an octave up in a major register, tense is a quiet, sustained
    minor-second cluster.
    """
    partials = _PAD_CHORDS[recipe]
    chord = sum(np.sin(2 * np.pi * frequency * time) for frequency in partials) / len(partials)
    duration_ms = time.size / SAMPLE_RATE * 1000
    attack_ms = min(1500.0, duration_ms * 0.3)
    release_ms = min(1500.0, duration_ms * 0.3)
    envelope = _attack_release_envelope(time.size, attack_ms, release_ms)
    tremolo = 1.0 + 0.08 * np.sin(2 * np.pi * 0.15 * time)
    pad = _PAD_GAIN[recipe] * np.asarray(chord, dtype=np.float64) * envelope * tremolo
    return np.asarray(pad, dtype=np.float64)


def _attack_release_envelope(count: int, attack_ms: float, release_ms: float) -> np.ndarray:
    envelope = np.ones(count, dtype=np.float64)
    attack = min(count, max(1, int(SAMPLE_RATE * attack_ms / 1000)))
    release = min(count, max(1, int(SAMPLE_RATE * release_ms / 1000)))
    if attack > 0:
        envelope[:attack] = np.linspace(0.0, 1.0, attack, endpoint=False)
    if release > 0:
        envelope[count - release :] = np.minimum(
            envelope[count - release :], np.linspace(1.0, 0.0, release)
        )
    return envelope


def _finalize(signal: np.ndarray, recipe: str) -> np.ndarray:
    """Bound a loop's seam or a one-shot's tail so neither clicks.

    Loopable beds (ambience + music pads) get their last sample forced to match the
    first, which is inaudible for these stationary/periodic textures and lets the mixer's
    crossfade-loop splice cleanly. One-shot SFX (thunder, door, glass, ...) must never be
    seam-forced this way -- snapping a percussive decay's tail back up to the (loud) head
    sample injects an audible click -- so they get a short linear fade-out tail instead.
    """
    if signal.size <= 1:
        return signal
    signal = signal.copy()
    if recipe in LOOPABLE_RECIPES:
        signal[-1] = signal[0]
        return signal
    tail = min(signal.size, max(1, int(SAMPLE_RATE * ONE_SHOT_FADE_MS / 1000)))
    signal[-tail:] *= np.linspace(1.0, 0.0, tail)
    return signal


def _one_shot(
    recipe: str,
    count: int,
    time: np.ndarray,
    rng: np.random.Generator,
    noise: np.ndarray,
) -> np.ndarray:
    del rng
    decay = {"thunder": 1.4, "door": 8, "knock": 14, "footsteps": 3, "glass": 10}
    envelope = np.exp(-time * decay.get(recipe, 5))
    if recipe == "thunder":
        return 0.22 * _moving_average(noise, 170) * envelope
    if recipe in {"door", "knock"}:
        pulse = np.sin(2 * np.pi * (95 if recipe == "door" else 180) * time)
        return 0.2 * pulse * envelope
    if recipe == "footsteps":
        signal = np.zeros(count)
        for position in range(0, count, max(1, SAMPLE_RATE // 2)):
            end = min(count, position + SAMPLE_RATE // 12)
            local = np.arange(end - position) / SAMPLE_RATE
            signal[position:end] += 0.16 * np.sin(2 * np.pi * 110 * local) * np.exp(-local * 35)
        return signal
    if recipe == "glass":
        tones = sum(np.sin(2 * np.pi * frequency * time) for frequency in (1300, 1900, 2700))
        return 0.06 * tones * envelope + 0.04 * noise * envelope
    return 0.01 * noise


def _moving_average(values: np.ndarray, width: int) -> np.ndarray:
    bounded = max(1, min(width, values.size))
    if bounded == 1:
        return values
    padded = np.pad(values, (bounded - 1, 0), mode="edge")
    cumulative = np.cumsum(np.insert(padded, 0, 0.0))
    return np.asarray(
        (cumulative[bounded:] - cumulative[:-bounded]) / bounded,
        dtype=np.float64,
    )


def _write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(samples.tobytes())
