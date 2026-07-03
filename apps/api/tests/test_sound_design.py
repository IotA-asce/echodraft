import json
import struct
import time
import wave
from pathlib import Path

from audio_fixtures import wav_bytes


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
