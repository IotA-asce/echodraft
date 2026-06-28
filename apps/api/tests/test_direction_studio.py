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


def project_with_segment(client) -> tuple[str, str, str]:
    project = client.post(
        "/api/v1/projects", json={"title": "Direction Studio", "rightsStatus": "declared"}
    ).json()["id"]
    imported = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "direction.txt",
                b"Chapter 1\n\nHurry now! The signal is fading.\n\nThe rain softened.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert wait_for_job(client, imported["id"])["status"] == "succeeded"
    structured = client.post(f"/api/v1/projects/{project}/structure/extract", json={}).json()
    assert wait_for_job(client, structured["id"])["status"] == "succeeded"
    chapter = client.get(f"/api/v1/projects/{project}/chapters").json()[0]["id"]
    scene = client.get(f"/api/v1/chapters/{chapter}/scenes").json()[0]["id"]
    segment = client.get(f"/api/v1/scenes/{scene}/segments").json()[0]["id"]
    return project, chapter, segment


def direction(segment_id: str, emotion: str, intensity: float) -> dict:
    return {
        "scopeType": "segment",
        "scopeId": segment_id,
        "pace": 1.1,
        "intensity": intensity,
        "tone": emotion,
        "emotion": emotion,
        "pauseBeforeMs": 50,
        "pauseAfterMs": 180,
        "stylePrompt": f"{emotion} delivery",
        "emphasis": emotion == "urgent",
        "whisper": False,
        "noSfx": True,
    }


def test_segment_direction_changes_render_fingerprint(client) -> None:
    project, chapter, segment = project_with_segment(client)
    client.put("/api/v1/settings/tts", json={"provider": "mock"})
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Narrator", "backend": "mock", "providerVoiceId": "mock-narrator"},
    ).json()
    client.put(
        f"/api/v1/projects/{project}/production-settings",
        json={"narratorVoiceProfileId": voice["id"]},
    )

    saved = client.put(
        f"/api/v1/projects/{project}/segments/{segment}/direction",
        json={"direction": direction(segment, "urgent", 0.8), "userLocked": True},
    ).json()
    assert saved["direction"]["emotion"] == "urgent"
    assert saved["userLocked"] is True
    produced = client.post(f"/api/v1/projects/{project}/chapters/{chapter}/produce").json()
    assert wait_for_job(client, produced["id"])["status"] == "succeeded"
    render = client.get(f"/api/v1/projects/{project}/segments/{segment}/renders").json()[0]
    metadata = json.loads(Path(render["metadataPath"]).read_text(encoding="utf-8"))
    assert metadata["direction"]["emotion"] == "urgent"
    assert metadata["direction"]["pauseAfterMs"] == 180
    status = client.get(f"/api/v1/projects/{project}/chapters/{chapter}/production-status").json()
    assert status["currentSegments"] == status["totalSegments"]

    client.put(
        f"/api/v1/projects/{project}/segments/{segment}/direction",
        json={"direction": direction(segment, "quiet", 0.25), "userLocked": True},
    )
    stale_status = client.get(
        f"/api/v1/projects/{project}/chapters/{chapter}/production-status"
    ).json()
    assert stale_status["currentSegments"] == stale_status["totalSegments"] - 1

    inferred = client.post(f"/api/v1/projects/{project}/directions/infer", json={}).json()
    assert wait_for_job(client, inferred["id"])["status"] == "succeeded"
    locked_direction = client.get(
        f"/api/v1/projects/{project}/segments/{segment}/direction"
    ).json()
    assert locked_direction["direction"]["emotion"] == "quiet"
