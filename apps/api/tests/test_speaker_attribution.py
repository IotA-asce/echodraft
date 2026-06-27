import json
import time
from pathlib import Path


def wait_for_job(client, job_id: str) -> dict:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_speaker_attribution_review_and_production_voice_resolution(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Cast Review", "rightsStatus": "declared"}
    ).json()["id"]
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    narrator_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    mara_voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Mara", "backend": "mock", "providerVoiceId": "mock-mara"},
    ).json()
    character = client.post(
        f"/api/v1/projects/{project}/characters",
        json={"displayName": "Mara", "aliases": ["Captain Vale"]},
    ).json()
    client.patch(
        f"/api/v1/characters/{character['id']}",
        json={"voiceProfileId": mara_voice["id"]},
    )
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": narrator_voice["id"]},
    )
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "cast.txt",
                b"Chapter 1\n\nMara: We leave now.\n\n\"Who is there?\"\n\nThe rain answered.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"

    attribution_job = client.post(
        f"/api/v1/projects/{project}/speaker-attributions/run", json={}
    ).json()
    assert wait_for_job(client, attribution_job["id"])["status"] == "succeeded"
    attributions = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    mara_row = next(item for item in attributions if item["speakerName"] == "Mara")
    unknown_row = next(item for item in attributions if item["status"] == "needs_review")
    assert mara_row["characterId"] == character["id"]
    assert mara_row["voiceProfileId"] == mara_voice["id"]
    assert unknown_row["speakerName"] is None

    reviewed = client.patch(
        f"/api/v1/speaker-attributions/{unknown_row['id']}",
        json={"characterId": character["id"], "status": "approved", "userLocked": True},
    ).json()
    assert reviewed["voiceProfileId"] == mara_voice["id"]
    rerun = client.post(f"/api/v1/projects/{project}/speaker-attributions/run", json={}).json()
    assert wait_for_job(client, rerun["id"])["status"] == "succeeded"
    locked = client.get(f"/api/v1/projects/{project}/speaker-attributions").json()
    assert next(item for item in locked if item["id"] == unknown_row["id"])["userLocked"] is True

    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]
    scene = client.get(f"/api/v1/chapters/{chapter['id']}/scenes").json()[0]
    segments = client.get(f"/api/v1/scenes/{scene['id']}/segments").json()
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter['id']}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    dialogue_segment = next(item for item in segments if item["speakerCandidate"] == "Mara")
    renders = client.get(
        f"/api/v1/projects/{project}/segments/{dialogue_segment['id']}/renders"
    ).json()
    metadata = json.loads(Path(renders[0]["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["voiceProfileId"] == mara_voice["id"]
