import json
import struct
import time
import wave
from pathlib import Path

import numpy as np

from audio_fixtures import wav_bytes
from echodraft_api.assembly import ChapterAssembler, SoundCueInput


def _ambience_cue(*, ducking: bool = False) -> SoundCueInput:
    return SoundCueInput(
        id="cue",
        scene_id="scene",
        asset_id="asset",
        name="room",
        asset_path="room.wav",
        asset_type="ambience",
        cue_type="ambience",
        start_ms=0,
        gain_db=-12.0,
        fade_in_ms=0,
        fade_out_ms=0,
        ducking=ducking,
        render_mode="light",
        no_sfx=False,
    )


def test_ambience_loop_crossfade_leaves_no_seam_discontinuity() -> None:
    # A short asset whose loop does NOT line up (3.3 cycles): a hard tile would jump ~0.96
    # at each seam. The 250 ms equal-power crossfade must keep every step small.
    length = 1_000
    phase = np.arange(length)
    asset = np.sin(2 * np.pi * 3.3 * phase / length)
    xfade = 200

    looped = ChapterAssembler._tile_with_crossfade(asset, 5_000, xfade)
    assert looped.size == 5_000
    assert float(np.max(np.abs(np.diff(looped)))) < 0.3

    # A naive (crossfade-disabled) tile of the same asset would break that bound, proving
    # the crossfade is what smooths the seam.
    naive = np.tile(asset, 5)[:5_000]
    assert float(np.max(np.abs(np.diff(naive)))) > 0.3


def test_duck_curve_ramps_between_full_and_attenuated_levels() -> None:
    assembler = ChapterAssembler.__new__(ChapterAssembler)
    count = int(ChapterAssembler.sample_rate * 0.5)
    curve = assembler._duck_curve(count, _ambience_cue(ducking=True))

    ducked = 10 ** (-6.0 / 20)
    # Body sits at the -6 dB duck; the transition passes through intermediate gains rather
    # than stepping instantly (no zipper).
    assert np.isclose(curve[count // 2], ducked, atol=1e-6)
    intermediate = curve[(curve > ducked + 1e-3) & (curve < 1.0 - 1e-3)]
    assert intermediate.size > 0
    # A non-ducked cue keeps unity gain end to end.
    flat = assembler._duck_curve(count, _ambience_cue(ducking=False))
    assert np.allclose(flat, 1.0)


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def project_with_produced_chapter(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Sound Design", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={"file": ("sound.txt", b"Chapter 1\n\nA quiet room waits.", "text/plain")},
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    return project, chapter, scene


def test_sound_design_import_assign_and_mix(client) -> None:
    project, chapter, scene = project_with_produced_chapter(client)
    clean_status = client.get(
        f"/api/v1/projects/{project}/chapters/{chapter}/production-status"
    ).json()
    assert clean_status["activeRender"]["renderMode"] == "speech_only"
    assert clean_status["activeRender"]["mixedAudioPath"] is None

    asset = client.post(
        f"/api/v1/projects/{project}/sound-assets",
        files={"file": ("room.wav", wav_bytes(), "audio/wav")},
        data={"asset_type": "ambience", "license_note": "synthetic test fixture"},
    ).json()
    assert asset["assetType"] == "ambience"
    assert asset["durationMs"] == 600
    assert Path(asset["assetPath"]).is_file()

    cue = client.post(
        f"/api/v1/projects/{project}/sound-cues",
        json={
            "sceneId": scene,
            "assetId": asset["id"],
            "cueType": "ambience",
            "gainDb": -12,
            "fadeInMs": 0,
            "fadeOutMs": 0,
            "ducking": True,
            "renderMode": "light",
        },
    ).json()
    assert cue["sceneId"] == scene
    assert cue["assetId"] == asset["id"]

    cues = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/sound-cues").json()
    assert [item["id"] for item in cues] == [cue["id"]]

    mixed = client.post(
        f"/api/v1/projects/{project}/chapters/{chapter}/assemble",
        json={"renderMode": "light"},
    ).json()
    assert mixed["renderMode"] == "light_cinematic"
    assert mixed["mixedAudioPath"]
    assert mixed["ambienceStemPath"]
    assert mixed["audioUrl"]

    manifest = json.loads(Path(mixed["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["soundDesign"]["mode"] == "light"
    assert manifest["soundDesign"]["cueCount"] == 1
    assert manifest["ambienceInputs"][0]["assetId"] == asset["id"]

    with wave.open(mixed["ambienceStemPath"]) as stem:
        stem_samples = struct.unpack(f"<{stem.getnframes()}h", stem.readframes(stem.getnframes()))
    with wave.open(mixed["mixedAudioPath"]) as output:
        mixed_samples = struct.unpack(
            f"<{output.getnframes()}h", output.readframes(output.getnframes())
        )
    assert max(abs(sample) for sample in stem_samples) > 0
    assert max(abs(sample) for sample in mixed_samples) > 0
