from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
SCHEMA_VERSION = "tier0-sound-1.0.0"
LICENSE_NOTE = (
    "CC0-1.0: project-authored procedural synthesis recipe dedicated to the public domain."
)


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
)


class TierZeroSoundBank:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root

    def resolve(
        self,
        tags: list[str],
        *,
        asset_type: str,
        duration_ms: int,
    ) -> ResolvedTierZeroAsset:
        normalized = {tag.strip().casefold().replace("-", "_") for tag in tags if tag.strip()}
        candidates = [entry for entry in BANK if entry.asset_type == asset_type]
        if not candidates:
            raise ValueError(f"Unsupported Tier-0 asset type: {asset_type}.")
        entry = sorted(
            candidates,
            key=lambda item: (-_jaccard(normalized, set(item.tags)), item.id),
        )[0]
        bounded_duration = max(250, min(60_000, duration_ms))
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "entryId": entry.id,
            "durationMs": bounded_duration,
        }
        cache_key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        root = self.cache_root / cache_key[:2] / cache_key
        path = root / "asset.wav"
        if not path.is_file():
            root.mkdir(parents=True, exist_ok=True)
            samples = _synthesize(entry.recipe, bounded_duration, seed=int(cache_key[:16], 16))
            _write_wav(path, samples)
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


def _synthesize(recipe: str, duration_ms: int, *, seed: int) -> np.ndarray:
    count = max(1, int(SAMPLE_RATE * duration_ms / 1000))
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(count)
    time = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    if recipe == "room":
        signal = 0.012 * _moving_average(noise, 9)
    elif recipe == "wind":
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
    else:
        signal = _one_shot(recipe, count, time, rng, noise)
    signal = np.clip(signal, -0.35, 0.35)
    if count > 1:
        signal[-1] = signal[0]
    return np.asarray(signal * 32767, dtype="<i2")


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


def _write_wav(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(samples.tobytes())
