import wave
from pathlib import Path

import numpy as np
import pytest

from echodraft_api.audio_analysis import analyze_wav
from echodraft_api.tier0_sound import LICENSE_NOTE, TierZeroSoundBank


def test_tier_zero_bank_resolves_deterministic_cached_rain(tmp_path: Path) -> None:
    bank = TierZeroSoundBank(tmp_path / "cache")

    first = bank.resolve(
        ["exterior", "rain", "night"],
        asset_type="ambience",
        duration_ms=1_000,
    )
    first_bytes = first.path.read_bytes()
    second = bank.resolve(
        ["rain", "night", "exterior"],
        asset_type="ambience",
        duration_ms=1_000,
    )

    assert first.entry.id == "rain"
    assert second.path == first.path
    assert second.cache_key == first.cache_key
    assert second.path.read_bytes() == first_bytes
    analysis = analyze_wav(first.path)
    assert analysis.duration_ms == 1_000
    assert -60 < analysis.rms_dbfs < -10
    assert analysis.clipped_sample_count == 0
    with wave.open(str(first.path), "rb") as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
    assert samples[0] == samples[-1]


def test_tier_zero_bank_resolves_sparse_sfx_and_cc0_manifest(tmp_path: Path) -> None:
    asset = TierZeroSoundBank(tmp_path / "cache").resolve(
        ["door_slam", "interior"],
        asset_type="sfx",
        duration_ms=750,
    )

    assert asset.entry.id == "door_slam"
    assert asset.path.is_file()
    manifest = asset.path.with_name("manifest.json").read_text(encoding="utf-8")
    assert LICENSE_NOTE in manifest


def test_tier_zero_api_materializes_normal_project_asset_and_reuses_it(client) -> None:
    project_id = client.post(
        "/api/v1/projects",
        json={"title": "Tier zero sound", "rightsStatus": "declared"},
    ).json()["id"]
    payload = {
        "tags": ["forest", "wind", "exterior"],
        "assetType": "ambience",
        "durationMs": 1_500,
    }

    first = client.post(
        f"/api/v1/projects/{project_id}/sound-assets/tier0", json=payload
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/sound-assets/tier0", json=payload
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["provenance"] == "bank"
    assert first.json()["licenseNote"] == LICENSE_NOTE
    assert Path(first.json()["assetPath"]).is_file()
    assert len(client.get(f"/api/v1/projects/{project_id}/sound-assets").json()) == 1


def test_tier_zero_sfx_lookup_degrades_to_no_cue_for_unsupported_event(tmp_path: Path) -> None:
    bank = TierZeroSoundBank(tmp_path / "cache")

    # A supported event type still resolves to its own dedicated asset...
    footsteps = bank.resolve(["footsteps"], asset_type="sfx", duration_ms=1_000)
    assert footsteps.entry.id == "footsteps"

    # ...but an event type the bundled bank has no asset for (e.g. "gunshot") must not be
    # substituted with the nearest-but-wrong entry: silence is safe, a wrong SFX is not.
    with pytest.raises(ValueError):
        bank.resolve(["gunshot"], asset_type="sfx", duration_ms=1_000)


def test_tier_zero_one_shot_sfx_gets_fade_tail_not_seam_forced(tmp_path: Path) -> None:
    bank = TierZeroSoundBank(tmp_path / "cache")

    thunder = bank.resolve(["thunder", "storm"], asset_type="sfx", duration_ms=1_200)
    with wave.open(str(thunder.path), "rb") as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")

    # A one-shot must never have its tail sample forced to match the head (that would
    # inject an audible click into a percussive decay); it fades linearly to true zero.
    assert samples[-1] == 0
    analysis = analyze_wav(thunder.path)
    assert analysis.clipped_sample_count == 0


def test_tier_zero_room_tone_reuses_mastering_room_tone_at_44100hz(tmp_path: Path) -> None:
    room = TierZeroSoundBank(tmp_path / "cache").resolve(
        ["interior", "quiet", "room"], asset_type="ambience", duration_ms=1_000
    )

    with wave.open(str(room.path), "rb") as audio:
        assert audio.getframerate() == 44_100
    analysis = analyze_wav(room.path)
    # mastering.ROOM_TONE_RMS_DBFS is ~ -70 dBFS; a wide band confirms reuse without
    # coupling this test to the exact pink-noise implementation.
    assert -80 < analysis.rms_dbfs < -60
    assert analysis.clipped_sample_count == 0


def test_tier_zero_music_pads_are_loopable_mood_parameterized_and_unclipped(
    tmp_path: Path,
) -> None:
    bank = TierZeroSoundBank(tmp_path / "cache")

    somber = bank.resolve(["somber", "music"], asset_type="music", duration_ms=6_000)
    bright = bank.resolve(["bright", "music"], asset_type="music", duration_ms=6_000)
    tense = bank.resolve(["tense", "music"], asset_type="music", duration_ms=6_000)

    assert {somber.entry.id, bright.entry.id, tense.entry.id} == {
        "music_pad_somber",
        "music_pad_bright",
        "music_pad_tense",
    }
    for resolved in (somber, bright, tense):
        with wave.open(str(resolved.path), "rb") as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        assert samples[0] == samples[-1]  # seam-forced: safe to loop
        analysis = analyze_wav(resolved.path)
        assert analysis.clipped_sample_count == 0
        assert -70 < analysis.rms_dbfs < -5  # gentle pad, present but not near-silent
