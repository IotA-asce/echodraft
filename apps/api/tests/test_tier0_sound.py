import wave
from pathlib import Path

import numpy as np

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
